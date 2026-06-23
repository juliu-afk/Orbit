# 阶段2 技术方案 —— ResourceGuard 熔断器

> 基于 `docs/PRD+ADR_Step7.3_ResourceGuard熔断器.md`（验收标准 3 条），本次技术方案覆盖 3 条，无偏离。

## 需求回顾

| # | 验收标准 | 本次 |
|---|---------|------|
| AC1 | 熔断决策 `allow_request()` P99 <12ms（10000次） | ✅ 纯内存，无 IO |
| AC2 | 熔断触发准确率 ≥95%（100 场景：50 Token+50 API） | ✅ 令牌桶+滑动窗口双判 |
| AC3 | 每级降级路径可独立验证，降级后成功率 ≥80% | ✅ 4 级降级链路 |

## 已有代码分析

`gateway/circuit_breaker.py` 已实现：三态机 + 连续失败 + 滑动窗口错误率。缺失：

| 能力 | 已有 | 需新增 |
|------|------|--------|
| 三态机 (CLOSED/OPEN/HALF_OPEN) | ✅ | - |
| 连续失败熔断 | ✅ | - |
| 错误率窗口熔断 | ✅ | - |
| 令牌桶突发容忍 | ❌ | `TokenBucket` |
| 单任务 Token 预算熔断 | ❌ | `BudgetGuard` |
| 多级降级链路 | ❌ | `DegradationPath` |
| 审计事件记录 | ❌ | `ResourceAudit` |
| 与 7.2 metrics 集成 | ❌ | 推送到已有 Gauge |

## 设计决策

**新建 `src/orbit/resource_guard/`，不修改已有 `circuit_breaker.py`。**

理由：
- `CircuitBreaker` 职责单一（API 失败熔断），已工作良好
- `ResourceGuard` 聚焦资源预算（Token 消耗/沙箱池），是互补层
- 两层可独立演进，ResourceGuard 内部可复用 CircuitBreaker

## 模块设计

### 新增文件

```
src/orbit/resource_guard/
├── __init__.py          # 导出
├── token_bucket.py      # 令牌桶算法
├── budget_guard.py      # 单任务 Token 预算熔断
├── degradation.py       # 4 级降级路径
├── resource_guard.py    # ResourceGuard 主入口
└── models.py            # 数据模型
```

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/orbit/core/config.py` | +ResourceGuard 配置项 |
| `tests/unit/test_resource_guard.py` | 新测试 (~15 用例) |

### 核心类设计

#### 1. `TokenBucket` (`token_bucket.py`)

```
令牌桶：容量 capacity，速率 rate（令牌/秒）。
allow(n) → bool: 消耗 n 个令牌，够则 True 否则 False。
纯内存 O(1)，无锁（单线程 asyncio）。
```

#### 2. `BudgetGuard` (`budget_guard.py`)

```
单任务 Token 预算守卫。
- set_budget(task_id, max_tokens)：设置预算
- record_usage(task_id, tokens)：记录消耗
- is_over_budget(task_id) → bool：超过预算 × 1.5 倍？
- 超限时触发局部熔断（仅该任务），不影响其他任务
```

#### 3. `DegradationPath` (`degradation.py`)

```
4 级降级：
L1: 切换备用模型 (deepseek→qwen) → 已有 LLMClient 实现
L2: 本地规则引擎 → 返回预定义响应模板
L3: 缓存数据（标记 stale） → 返回上次成功结果的缓存
L4: 转人工挂起 → 返回 TASK_SUSPENDED 状态
```

#### 4. `ResourceGuard` (`resource_guard.py`)

```
主入口，组合以上：
- guard_request(task_id, estimated_tokens) → Decision(allow/deny, degradation_level)
- record_result(task_id, success: bool, tokens_used: int)
- get_state() → ResourceGuardState
- 决策纯内存，目标 P99 <12ms
```

### 数据流

```
调度器 → ResourceGuard.guard_request()
  ├─ TokenBucket.allow(tokens)        # 全局令牌桶
  ├─ BudgetGuard.is_over_budget(id)   # 单任务预算
  ├─ CircuitBreaker.before_call()     # 已有 API 熔断
  └─ → Decision(allow=bool, level=int)
        ├─ allow → 正常调用 LLM
        └─ deny  → DegradationPath.execute(level)
                      ├─ L1: 切备用模型
                      ├─ L2: 规则引擎模板
                      ├─ L3: 缓存数据
                      └─ L4: 挂起人工

ResourceGuard.record_result()
  ├─ TokenBudget.record_usage()
  ├─ CircuitBreaker.record_success/failure()
  └─ 推送指标到 orbit_circuit_breaker_state Gauge
     推送事件到 EventBus (agentops:alert)
```

## API 设计

无新 REST 端点。ResourceGuard 是内部服务，通过已有端点暴露：
- `GET /api/v1/observability/metrics` — `circuit_breaker_state` 字段已存在
- `GET /api/v1/observability/alerts` — 熔断告警通过 EventBus 推送
- `GET /api/v1/observability/health` — 新增 `resource_guard` 组件

## 测试策略

| 测试 | 用例 | 覆盖 |
|------|------|------|
| TokenBucket | 4 | 创建/消费/补充/拒绝/突发 |
| BudgetGuard | 3 | 预算设置/消耗/超限熔断/多任务隔离 |
| DegradationPath | 3 | L1-L4 各级返回正确、降级失败跳下一级 |
| ResourceGuard | 5 | 组合判断/延迟基准/状态转换/审计事件 |
| 性能 | 2 | `allow_request()` P99 <12ms (pytest-benchmark) |
| **合计** | **~17** | |

## 与 PRD 对照

| PRD 验收标准 | 方案 | 代码位置 |
|-------------|------|---------|
| AC1: P99 <12ms | TokenBucket O(1), BudgetGuard dict lookup, 全部纯内存 | `resource_guard/token_bucket.py` + `resource_guard.py` |
| AC2: ≥95% 准确率 | TokenBucket 限流 + BudgetGuard 超预算 ×1.5 + CircuitBreaker 已有 | `resource_guard/budget_guard.py` |
| AC3: 4 级降级可切换 | DegradationPath 各级独立验证 | `resource_guard/degradation.py` |

## 风险

| 风险 | 缓解 |
|------|------|
| 已有 CircuitBreaker 被修改 | 不碰——ResourceGuard 是包装层 |
| TokenBucket 精度 | 用 time.monotonic() 而非 time.time()，容忍亚毫秒误差 |
| 降级 L2/L3 无实际实现 | L2 返回固定模板，L3 返回占位缓存——MVP 可用，后续扩展 |
