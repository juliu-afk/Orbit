# 阶段 3 实现记录 — CUA 模式迁移 Phase A

> 日期：2026-07-05 | 基于：[阶段2-技术方案-CUA模式迁移.md](阶段2-技术方案-CUA模式迁移.md)

## 方案引用

| 设计决策 | 是否按方案实现 | 备注 |
|---------|:--:|------|
| 常量配置：TOOL_TIMEOUT_SECONDS / ACTION_DEBOUNCE_SECONDS / MAX_AGENT_CYCLES | ✅ | 按方案 §2.2 |
| GraphNode.serialize_tools 字段 | ✅ | 按方案 §2.3 |
| 循环计数器 + 上限检查 | ✅ | 按方案 §3.1 |
| CODING 串行化 `parallel_tool_calls=False` | ✅ | 按方案 §3.1 |
| 防抖延迟 CODING→VERIFYING | ✅ | 按方案 §3.1 |
| _run_agent 超时按状态分级 | ✅ | 按方案 §3.1 |
| L2ReflectionResult / L4BehaviorResult / L5ContractResult 模型 | ✅ | 按方案 §2.1 |
| L2 预测 vs 实际对比 + deviation_score | ✅ | 按方案 §3.2，公式 `min(len(unexpected)/max(len(pred_set),1), 1.0)` |
| L4 自述行为 vs mypy 推断对比 | ✅ | 按方案 §3.2 |
| L5 自述契约 vs Z3 验证对比 + _describe_contract | ✅ | 按方案 §3.2 |
| 向后兼容——新参数默认 None | ✅ | 按方案风险 R5 |

## 改动清单

| 文件 | 操作 | 行数 | 目的 |
|------|:--:|:--:|------|
| `src/orbit/hallucination/schemas.py` | 修改 | +46 | 新增 3 个反思结果模型 |
| `src/orbit/hallucination/l2_dynamic.py` | 修改 | +60/-10 | L2 反思式函数调用对比 |
| `src/orbit/hallucination/l4_type.py` | 修改 | +40/-6 | L4 反思式行为对比 |
| `src/orbit/hallucination/l5_z3.py` | 修改 | +71/-10 | L5 反思式契约对比 + `_describe_contract` |
| `src/orbit/scheduler/graph.py` | 修改 | +2 | GraphNode 新增 serialize_tools |
| `src/orbit/scheduler/task_runner.py` | 修改 | +69/-8 | 循环上限/超时/防抖/串行化 |

## 偏差说明

严格按方案实现，无偏离。

## 回溯对照

| PRD 验收标准 | 方案设计决策 | 代码位置 |
|------------|------------|---------|
| AC1 工具级超时 | §3.1 `_run_agent` 超时按状态分级 | [task_runner.py:289](src/orbit/scheduler/task_runner.py#L289) `tool_timeout` 注入 + [task_runner.py:291](src/orbit/scheduler/task_runner.py#L291) `timeout` 默认 None |
| AC2 CODING 串行化 | §2.3 `GraphNode.serialize_tools` + §3.1 | [graph.py:47](src/orbit/scheduler/graph.py#L47) `serialize_tools` + [task_runner.py:172](src/orbit/scheduler/task_runner.py#L172) `parallel_tool_calls=False` |
| AC3 循环上限 50 轮 | §3.1 `cycle_count > MAX_AGENT_CYCLES → FAILED` | [task_runner.py:150-170](src/orbit/scheduler/task_runner.py#L150) 循环计数器+上限 |
| AC4 防抖延迟 120ms | §3.1 `asyncio.sleep(ACTION_DEBOUNCE_SECONDS)` | [task_runner.py:196-198](src/orbit/scheduler/task_runner.py#L196) `_DEBOUNCE_TRANSITIONS` |
| AC5 L2 预测字段 | §2.1 `L2ReflectionResult` + §3.2 | [schemas.py:61](src/orbit/hallucination/schemas.py#L61) 模型 + [l2_dynamic.py:153](src/orbit/hallucination/l2_dynamic.py#L153) 偏差分计算 |
| AC6 L4 行为对比 | §2.1 `L4BehaviorResult` + §3.2 | [schemas.py:74](src/orbit/hallucination/schemas.py#L74) 模型 + [l4_type.py:96](src/orbit/hallucination/l4_type.py#L96) 行为对比 |
| AC7 L5 契约对比 | §2.1 `L5ContractResult` + §3.2 | [schemas.py:86](src/orbit/hallucination/schemas.py#L86) 模型 + [l5_z3.py:73](src/orbit/hallucination/l5_z3.py#L73) 契约对比 |
| AC8 现有测试全通过 | §5 不改变判定逻辑 | 所有新增参数默认 None，不传时完全向后兼容 |
