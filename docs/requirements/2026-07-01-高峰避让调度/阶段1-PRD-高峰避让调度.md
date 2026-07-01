# PRD：LLM 高峰避让延迟调度

> 版本: v1.0 | 日期: 2026-07-01 | 状态: 待确认
> 基于: Goal 模式 + Loop 模式 + ResourceGuard + Gateway Routing 现有能力

---

## 1. 背景

当前 Orbit 有 8 种用户交互模式，其中 **Goal 批量模式**（`--from` 目录导入）可以一次性提交多个任务。但所有任务提交后**立即执行**，没有"等到低峰再跑"的能力。

### 1.1 痛点

- LLM API 存在事实上的高峰/低峰时段：工作日白天（尤其是 US Pacific 10:00-18:00）API 延迟高、排队久；深夜/周末 API 响应快、成本低
- 部分厂商（DeepSeek、GLM）已推出**分时定价**策略
- 用户有 10 个非紧急任务，希望批量提交后让系统在凌晨自动跑完
- 当前只能手动写 cron 表达式（Loop 模式），但用户不知道每个任务需要多少时间、如何编排

### 1.2 目标

让用户在提交 Goal 时说一句 **"非紧急，低峰执行"**，系统自动：
1. 识别当前是否高峰期
2. 将任务排队到低峰时段
3. 按优先级+预估耗时在低峰窗口内顺序执行
4. 低峰窗口不够用时，剩余任务排队到下一个低峰窗口

---

## 2. 用户故事

### P0

- **作为用户**，我提交 Goal 时指定 `defer_to_offpeak: true`，系统自动将任务延迟到下一个低峰窗口执行，不需要我手动算时间。
- **作为用户**，我能看到任务队列状态："排队中，预计 02:00 开始执行"、"执行中 (3/10)"、"已完成"。
- **作为系统**，我维护一份"厂商高峰时段表"，自动判定当前是否在高峰期内。

### P1

- **作为用户**，我可以自定义高峰时段（比如我的团队习惯晚上工作，把低峰定义为上午）。
- **作为运维人员**，我可以查看低峰窗口利用率报告——昨晚的窗口跑了多少任务、用了多少 Token、省了多少钱。
- **作为系统**，我在低峰窗口即将用完时，自动将未执行任务顺延到下一个窗口，并通知用户。

### P2

- **作为系统**，我分析历史 API 调用延迟数据，动态调整高峰时段定义（而不依赖静态配置）。
- **作为系统**，我支持跨厂商高峰避让——DeepSeek 高峰时切到 GLM（免费），GLM 也高峰时才排队。

---

## 3. 验收标准

### AC1: 高峰时段判定

| # | 标准 |
|---|------|
| AC1.1 | 系统内置 DeepSeek/GLM/Anthropic/OpenAI 四大厂商的默认高峰时段配置（时区感知） |
| AC1.2 | `GET /api/v1/schedule/peak-status` 返回当前是否高峰、下一个低峰窗口时间 |
| AC1.3 | 高峰判定考虑工作日/周末/节假日差异 |
| AC1.4 | 支持环境变量 `ORBIT_OFFPEAK_ONLY=true` 全局强制低峰执行（紧急任务走 `urgent` flag 例外） |

### AC2: 延迟执行队列

| # | 标准 |
|---|------|
| AC2.1 | Goal API 新增 `defer_to_offpeak: bool` 参数，默认 `false`（保持向后兼容） |
| AC2.2 | 提交 `defer_to_offpeak=true` 的 Goal 进入 `DeferredQueue`，不立即执行 |
| AC2.3 | `DeferredQueue` 持久化到 SQLite（`deferred_tasks` 表），重启不丢任务 |
| AC2.4 | 低峰窗口到达时，按优先级顺序 + DAG 依赖关系自动释放任务到 `ResourceScheduler` |
| AC2.5 | 用户可随时将排队中的任务改为立即执行（`urgent` flag），系统中断排队立即调度 |

### AC3: 低峰窗口管理

| # | 标准 |
|---|------|
| AC3.1 | `PeakWindowManager` 维护每个厂商的默认高峰时段配置 |
| AC3.2 | 预估每个排队任务的 Token 用量和时间（调用已有 `PreFlightEstimator`） |
| AC3.3 | 低峰窗口容量计算：窗口时长 vs 任务预估耗时，窗口满则顺延 |
| AC3.4 | 低峰窗口开始前 5 分钟预热（检查 API 可用性、模型状态） |

### AC4: 成本节省报告

| # | 标准 |
|---|------|
| AC4.1 | 每个延迟执行的任务在完成后对比"如果立即执行的估算成本"vs"实际执行成本" |
| AC4.2 | `GET /api/v1/schedule/savings-report` 返回累计节省金额、任务数、窗口利用率 |
| AC4.3 | 报告按厂商分拆，展示每个厂商的高峰/低峰 Token 分布 |

### AC5: 驾驶舱可见性

| # | 标准 |
|---|------|
| AC5.1 | 驾驶舱 Dashboard 显示"排队任务数"和"下一个低峰窗口倒计时" |
| AC5.2 | 任务列表展示每个任务的"计划执行时间"和"排队状态" |
| AC5.3 | 低峰窗口到期但任务未完成时，Dashboard 展示黄色告警 |

---

## 4. 数据契约

### 4.1 厂商高峰时段配置

```yaml
# configs/peak_windows.yaml（默认配置，可通过环境变量覆盖）
providers:
  deepseek:
    timezone: Asia/Shanghai
    peak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "09:00-23:00"        # 北京时间工作日白天+晚上
    offpeak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "23:00-09:00"        # 深夜到凌晨
      - days: [Sat, Sun]
        hours: "00:00-24:00"        # 周末全天
    # 分时定价倍数（高峰 1.0x，低峰 0.7x）
    peak_price_multiplier: 1.0
    offpeak_price_multiplier: 0.7

  anthropic:
    timezone: America/Los_Angeles
    peak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "08:00-18:00"        # US Pacific 工作时间
    offpeak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "18:00-08:00"
      - days: [Sat, Sun]
        hours: "00:00-24:00"

  openai:
    timezone: America/Los_Angeles
    peak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "08:00-18:00"

  glm:
    timezone: Asia/Shanghai
    peak_windows:
      - days: [Mon, Tue, Wed, Thu, Fri]
        hours: "09:00-23:00"
```

### 4.2 DeferredTask 模型

```python
class DeferredTask(BaseModel):
    """延迟执行任务——持久化到 deferred_tasks 表。"""

    id: str                          # UUID4，对应 GoalSession.id
    goal_description: str            # 目标描述（审计用）
    priority: TaskPriority           # 继承 Goal 优先级
    provider: str                    # 目标 LLM 提供商（deepseek/anthropic/openai/glm）
    estimated_tokens: int            # PreFlightEstimator 预估 Token
    estimated_duration_seconds: int  # 预估执行时间
    target_window_start: str         # 目标低峰窗口开始时间 ISO
    target_window_end: str           # 目标低峰窗口结束时间 ISO
    status: Literal["queued", "released", "running", "done", "urgent_override", "cancelled"]
    created_at: str
    released_at: str | None
    completed_at: str | None
    actual_tokens: int               # 实际消耗 Token（完成后填写）
    cost_saved_yuan: Decimal | None  # 节省金额（完成后计算）
```

### 4.3 PeakStatus API 响应

```json
{
  "code": 0,
  "data": {
    "is_peak": true,
    "current_provider_peaks": {
      "deepseek": {"is_peak": true, "peak_ends_at": "2026-07-01T23:00:00+08:00"},
      "anthropic": {"is_peak": false, "next_peak_at": "2026-07-02T08:00:00-07:00"}
    },
    "next_offpeak_window": {
      "provider": "deepseek",
      "starts_at": "2026-07-01T23:00:00+08:00",
      "ends_at": "2026-07-02T09:00:00+08:00",
      "duration_hours": 10.0,
      "queued_tasks_count": 5,
      "estimated_capacity_remaining": 3
    },
    "queue_summary": {
      "total_queued": 10,
      "urgent": 0,
      "by_provider": {"deepseek": 7, "anthropic": 3}
    }
  }
}
```

### 4.4 Goal API 扩展

```json
// POST /api/v1/goal 新增字段
{
  "description": "修复支付模块超时 Bug",
  "defer_to_offpeak": true,      // 新增：延迟到低峰执行
  "urgent": false,               // 新增：紧急任务——忽略高峰限制立即执行
  "target_provider": "deepseek", // 新增：指定目标厂商（用于判定该厂商的高峰/低峰）
  "max_price_multiplier": 0.8    // 新增：只在价格倍数 ≤0.8x 时执行（可选）
}
```

---

## 5. 技术方案概要

### 5.1 架构位置

```
src/orbit/
├── scheduler/
│   └── offpeak_scheduler.py    # 新增——OffPeakScheduler
├── resource_guard/
│   └── budget_guard.py         # 已有——不改
├── goal/
│   ├── models.py               # 扩展——DeferredTask 模型
│   ├── meta_orchestrator.py    # 扩展——defer_to_offpeak 分支
│   └── intake_router.py        # 已有——不改
├── api/routes/
│   └── schedule.py             # 新增——/api/v1/schedule/* 路由
├── gateway/
│   └── routing.py              # 扩展——peak_price_multiplier 维度
```

### 5.2 核心流程

```
用户提交 10 个 Goal (defer_to_offpeak=true)
  │
  ├── 1. IntakeRouter 判定（不改）
  │     └── 拆解为 N 个子任务
  │
  ├── 2. PreFlightEstimator 预估（已有）
  │     └── estimated_tokens + estimated_duration
  │
  ├── 3. OffPeakScheduler.enqueue()    【新增】
  │     ├── 查 PeakWindowManager → 确定目标厂商当前是否高峰
  │     ├── 高峰 → 计算下一个低峰窗口
  │     ├── 检查低峰窗口容量是否够
  │     │   ├── 够 → 入队，设置 target_window_start
  │     │   └── 不够 → 入队，顺延到再下一个窗口
  │     └── 持久化到 deferred_tasks 表
  │
  ├── 4. OffPeakScheduler._window_watcher()  【新增——asyncio 后台协程】
  │     ├── 每分钟检查：是否有窗口即将开始（≤5min）
  │     ├── 窗口到达 → 释放队内任务到 MetaOrchestrator
  │     ├── 窗口结束前 10min → 检查剩余容量
  │     │   ├── 够 → 释放更多任务
  │     │   └── 不够 → 顺延到下一个窗口，通知用户
  │     └── 窗口结束 → 暂停释放，未完成任务继续跑完
  │
  └── 5. MetaOrchestrator.run()（不改）
        └── 正常的 Goal→SubTask→Critique→Verify→Merge 流水线
```

### 5.3 窗口容量算法

```python
def estimate_window_capacity(
    window_start: datetime,
    window_end: datetime,
    queued_tasks: list[DeferredTask],
    max_parallel: int = 5,
) -> int:
    """估算低峰窗口能跑几个任务。

    WHY 悲观估算: 用预估耗时的 1.3x 做 buffer，防止预估偏差导致窗口溢出。
    """
    window_seconds = (window_end - window_start).total_seconds()
    # 排序：优先级高 + 耗时短的先跑（最大化吞吐）
    sorted_tasks = sorted(queued_tasks, key=lambda t: (t.priority.value, t.estimated_duration_seconds))
    
    remaining = window_seconds * max_parallel  # 并行容量
    count = 0
    for task in sorted_tasks:
        cost = task.estimated_duration_seconds * 1.3  # 30% buffer
        if remaining >= cost:
            remaining -= cost
            count += 1
        else:
            break
    return count
```

### 5.4 与现有模块的关系

| 现有模块 | 关系 | 说明 |
|---------|------|------|
| `ResourceScheduler` | **下游** | OffPeakScheduler 释放任务后交给 ResourceScheduler 执行 |
| `Loop` | **互补** | Loop 是用户手动指定 cron；OffPeak 是系统自动选时间 |
| `BudgetGuard` | **增强** | 低峰执行时 BudgetGuard 仍生效，双重保护 |
| `Gateway routing` | **增强** | `select_model()` 增加 `price_multiplier` 维度 |
| `PreFlightEstimator` | **复用** | 用已有预估能力填充 `estimated_tokens` 和 `estimated_duration` |
| `MetaOrchestrator` | **不感知** | MetaOrchestrator 不关心任务是怎么被触发的，保持解耦 |

---

## 6. 异常定义

| 场景 | 处理 |
|------|------|
| 低峰窗口到期但无可用 LLM key | 任务保持 `queued` 状态，顺延到下一个窗口，Dashboard 黄色告警 |
| 厂商分时定价数据过时 | 管理员可手动刷新配置（`POST /api/v1/schedule/reload-config`），默认每周自动重载 |
| 用户提交 `urgent=true` + `defer_to_offpeak=true` | `urgent` 优先级更高——忽略 `defer_to_offpeak`，立即执行 |
| `PreFlightEstimator` 预估严重偏低 | 实际执行超时的任务不阻断队列，但计入 `estimation_error` 指标供后续校准 |
| 节假日未被默认配置覆盖 | 支持 `ORBIT_HOLIDAYS_URL` 环境变量指向自定义节假日 JSON API |
| 所有厂商都处于高峰期 | 返回 `no_offpeak_window_available`，任务入队等待第一个恢复低峰的厂商 |
| `deferred_tasks` 表损坏 | 启动时自动检查 SQLite 完整性，损坏则从 WAL 恢复 + 告警 |

---

## 7. 成功标准

| # | 标准 | 衡量方式 |
|---|------|---------|
| SC1 | 用户一句"低峰执行"即可延迟调度，无需手动算 cron | 验收测试：提交 Goal → 系统返回 `target_window_start` |
| SC2 | 低峰窗口利用率 ≥ 80% | savings-report API 统计 |
| SC3 | 预估耗时与实际耗时偏差 ≤ 30% | estimation_error 指标 |
| SC4 | 重启不丢排队任务 | deferred_tasks 表持久化 + 集成测试 |
| SC5 | 紧急任务可立即执行（urgent flag） | 队列中有排队任务时，urgent 任务立即出队执行 |

---

## 8. 范围 (Do/Don't)

**Do:**
- 静态高峰时段配置 + 手动覆盖
- 延迟队列（SQLite 持久化）
- 低峰窗口容量估算
- 成本节省报告
- 驾驶舱排队视图

**Don't:**
- 不实现动态高峰检测（基于历史延迟数据）——那是 Phase 2
- 不自动跨厂商切换（如 DeepSeek 高峰 → GLM）——那是已有的 `DegradationPath` L1 逻辑，不在本 PRD 范围
- 不修改 MetaOrchestrator 核心流水线——OffPeakScheduler 是外围包装
- 不支持基于实时价格的自动竞价——厂商 API 暂不提供实时价格

---

## 9. 待定决策

| # | 问题 | 暂定 |
|---|------|------|
| Q1 | 高峰配置存 YAML 还是 SQLite？ | YAML 文件 + 环境变量覆盖（YAML 方便运维手动编辑，SQLite 方便运行时写入。先 YAML） |
| Q2 | 窗口 watcher 检查频率？ | 每分钟（太频繁浪费 CPU，太稀疏可能错过窗口） |
| Q3 | 是否需要支持"仅在价格 < X 元/1M tokens 时执行"？ | P1——`max_price_multiplier` 字段已预留 |
| Q4 | 低峰窗口内存任务超时未完成怎么办？ | 不强制中断——跑完为止。只是新任务不再释放到当前窗口 |
