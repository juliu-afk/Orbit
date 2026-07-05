# 阶段1 PRD：Orbit Phase D——Agent五大能力P2增强

> 日期：2026-07-05 | 分支：feat/agent-phase-d | 基础：PR#198合并后master

## 任务清单

| # | 任务 | 对标能力 | 目标 |
|---|------|---------|------|
| D1 | PreAct 预测规划 | ② 规划推理 | Action前先预测可能结果 |
| D2 | MCTS 多路径探索 | ② 规划推理 | 非线性规划替代单路径 |
| D3 | MCP Server 暴露 | ③ 工具调用 | Orbit自身工具供外部Agent调用 |
| D4 | VIGIL 自愈运行时 | ④ 闭环容错 | 诊断+修复自身行为 |
| D5 | Agentic Memory | ① 感知记忆 | 记忆直接驱动行动决策 |

## 背景

Phase A+B+C 完成后，Agent五大能力覆盖率：①80% ②65% ③90% ④70% ⑤55%。
Phase D 目标是全部达到 85%+。

## Non-Goals

- 不重复 Phase A/B/C 的工作
- 不引入新的 LLM 依赖（PreAct/MCTS 复用现有 gateway）
- MCP Server 不替代现有 tools/ 注册中心——作为补充暴露层
