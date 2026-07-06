# 阶段1 PRD — 五大能力模块集成接线

## 背景

2026-07-05 的"Orbit Agent 五大能力差距分析"识别了 13 项差距（P0×2 + P1×7 + P2×4）。截至 2026-07-07，所有 13 项差距的模块代码已编写完成（16 个模块，~3500 行），但集成验证发现 **11 项未接入或半接入执行循环**。

问题不是缺代码——是缺接线。

## 用户故事

| 优先级 | 故事 |
|--------|------|
| P0 | 作为 Orbit 用户，我希望 Agent 在每一步后反思是否偏离目标（ReflAct），以便财务/审计场景下不会自信地做错事 |
| P0 | 作为 Orbit 用户，我希望独立的 Monitor Agent 监控主 Agent 行为，在目标漂移/死循环/超时时告警或触发人工介入 |
| P1 | 作为 FDE，我希望 Agent 记住跨会话的关键事件和用户偏好，以便同时管理多个客户时不需要每次"第一次见面" |
| P1 | 作为 FDE，我希望 Orbit 从每次执行轨迹中自动蒸馏可复用策略，实现"碎石路→高速公路"的自动化 |
| P1 | 作为 Orbit 用户，我希望 Agent 出错后能诊断根因并尝试自愈，而不是简单回滚重试 |
| P2 | 作为 Orbit 用户，我希望 Agent 行动前预测结果（PreAct），探索多条路径（MCTS），减少回滚成本 |

## 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| AC1 | `ReflectionEngine` 在 Agent 创建时实例化，每轮 turn 后实际执行反思 | 日志中出现 `reflact_drift_detected` 或 `reflection_*` 事件 |
| AC2 | `PreActEngine` 在 Agent 创建时实例化，Action 前实际执行预测 | 日志中出现 `preact_skip` 事件 |
| AC3 | Monitor Agent 收到主 Agent 的执行事件（TOOL_RESULT），能产生告警 | Monitor 日志非空，`monitor_alert` 事件可见 |
| AC4 | 关键事件（工具错误/目标漂移/任务完成）写入情节记忆 | `episodic_events` 表非空 |
| AC5 | 工具执行错误时 VIGIL 尝试诊断并生成替代方案 | 日志中出现 `vigil_diagnose` 或等价事件 |
| AC6 | `maybe_distill()` 在蒸馏前经过 ANCHOR 检查点 | `anchor_supervisions` 表有 `before_distill` 记录 |
| AC7 | `ProfileStore` 在会话启动时加载用户画像，注入 system prompt | 用户画像数据影响 Agent 行为 |
| AC8 | `MCTSPlanner` 在复杂规划场景下可用（Architect Agent） | 代码路径可触发 |
| AC9 | 现有测试全部通过，覆盖率不下降 | CI 绿灯 |

## Non-Goals

- 不新增模块——只接线已有模块
- 不改模块内部逻辑——只改创建/调用点
- 不新增数据库迁移——现有模块的 SQLite schema 已内嵌

## 影响范围

- `task_runner/runner.py` — 创建 ReflectionEngine/PreActEngine/VigilSelfHealer 实例
- `agents/factory.py` — 传递 preact_engine 参数
- `agents/react_agent/agent.py` — 向 Monitor 推送事件、调用 record_event、VIGIL 诊断
- `integration/wiring.py` — ANCHOR pre-distill 检查、Monitor queue 暴露、Profile 加载
- `api/routes/sessions.py` 或 `chat.py` — 会话启动时加载用户画像
