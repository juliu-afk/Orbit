# 阶段3 实现记录 —— ResourceGuard 熔断器

## 方案引用

基于 [阶段2 技术方案](./阶段2-技术方案-ResourceGuard.md)。严格按方案实现，无偏离。

## 改动清单

| 文件 | 行数 | 目的 |
|------|------|------|
| `src/orbit/resource_guard/models.py` | 65 | 数据模型: GuardResult/CircuitState/BudgetRecord/ResourceGuardState |
| `src/orbit/resource_guard/token_bucket.py` | 63 | 令牌桶: O(1) 纯内存, 允许突发, P99 <1ms |
| `src/orbit/resource_guard/budget_guard.py` | 74 | 单任务 Token 预算: 超 ×1.5 局部熔断, 任务隔离 |
| `src/orbit/resource_guard/degradation.py` | 117 | 4 级降级: L1 备用模型/L2 规则/L3 缓存/L4 人工 |
| `src/orbit/resource_guard/resource_guard.py` | 234 | 主入口: 组合判断+三态机+审计事件+Prometheus 指标 |
| `src/orbit/resource_guard/__init__.py` | 27 | 导出 |
| `src/orbit/core/config.py` | +8 | ResourceGuard 配置项 (RESOURCE_GUARD_*) |
| `tests/unit/test_resource_guard.py` | 285 | 31 用例 |

## 技术决策记录

### 为什么不修改已有 CircuitBreaker
`gateway/circuit_breaker.py` 职责单一（API 失败熔断），已有 10 个测试，被 LLMClient 依赖。ResourceGuard 是上层资源预算层（Token 用量/降级），职责不同。两层独立演进，ResourceGuard 可注入已有 CircuitBreaker 做双重保护。

### 为什么令牌桶而不是漏桶
令牌桶允许突发（满桶时可一次消耗所有令牌），漏桶强制平滑。LLM 调用天然有突发特征（用户提交后短时间内大量 token 消耗），令牌桶更匹配。

### 为什么 L2/L3 降级是占位实现
L2 规则引擎返回预定义模板消息，L3 缓存返回占位数据。MVP 阶段够用（验证降级路径可切换），后续可接入真实规则引擎 (L2) 和 Redis 缓存 (L3)。

## 回溯对照

| PRD 验收标准 | 方案设计 | 代码位置 |
|-------------|---------|---------|
| AC1: P99 <12ms | TokenBucket O(1) + BudgetGuard dict lookup | `token_bucket.py:45` + `resource_guard.py:88-107` |
| AC2: ≥95% 准确率 | 令牌桶限流 + 预算 ×1.5 + 连续失败 5 次 | `budget_guard.py:37-42` + `resource_guard.py:144-156` |
| AC3: 4 级降级 | DegradationPath L1-L4, 各级独立验证 | `degradation.py:56-113` |

## 验证

- ruff: 零警告
- mypy --strict: 零错误
- pytest 全量: 通过
- guard_request() P99: <1ms (5000 次)
- 零新依赖
