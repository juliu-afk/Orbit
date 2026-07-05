# 阶段 2 技术方案 — CUA 模式迁移 Phase A

> 日期：2026-07-05 | 基于：[阶段1-PRD-CUA模式迁移.md](阶段1-PRD-CUA模式迁移.md)

## 0. 需求回顾

基于阶段1 PRD，Phase A 覆盖 2 个用户故事、8 条验收标准：

| # | 故事 | 验收标准数 |
|---|------|:--:|
| US1 | Agent 循环鲁棒性增强（工具级超时/防抖延迟/串行化/循环上限） | AC1-AC4 |
| US2 | 反思式 CoT Prompt（L2/L4/L5 三层"自述预期→对比实际"） | AC5-AC8 |

> 本次技术方案覆盖 8 条验收标准，无偏离。

## 1. 影响范围

### 1.1 US1 — 调度器鲁棒性

| 文件 | 操作 | 改动内容 |
|------|:--:|------|
| `src/orbit/scheduler/task_runner.py` | 修改 | `_agent_cycle` 加循环计数器+上限；`_run_agent` 加工具级超时+动作间延迟 |
| `src/orbit/scheduler/dag_runner.py` | 修改 | `_execute_node` 加串行化标志——CODING 节点禁用并行工具调用 |
| `src/orbit/scheduler/graph.py` | 修改 | `GraphNode` 新增 `serialize_tools: bool` 字段 |
| `tests/unit/test_scheduler/` | 新增 | `test_task_runner_robustness.py` |

### 1.2 US2 — 反思式 CoT

| 文件 | 操作 | 改动内容 |
|------|:--:|------|
| `src/orbit/hallucination/schemas.py` | 修改 | L2/L4/L5 结果模型新增反思对比字段 |
| `src/orbit/hallucination/l2_dynamic.py` | 修改 | 沙箱执行前预测→执行后对比→计算偏差分 |
| `src/orbit/hallucination/l4_type.py` | 修改 | Agent 代码附带自述行为→mypy 验证→对比实际 vs 预期 |
| `src/orbit/hallucination/l5_z3.py` | 修改 | Agent 附带自述契约→Z3 验证实际契约→对比 |
| `tests/unit/test_hallucination/` | 修改 | 新增反思式 CoT 验证用例 |

## 2. API / 数据模型设计

### 2.1 新增 schemas 字段

```python
# hallucination/schemas.py — 新增模型

class L2ReflectionResult(ValidationResult):
    """L2 反思式验证结果（新增）。"""
    predicted_calls: list[str] = Field(default_factory=list)   # Agent 预测将调用的函数
    actual_calls: list[str] = Field(default_factory=list)       # 实际追踪到的函数调用
    deviation_score: float = Field(0.0, ge=0.0, le=1.0)        # 偏差分（0=完全匹配, 1=完全偏离）
    unpredicted_calls: list[str] = Field(default_factory=list)  # 预测了但没调用的
    unexpected_calls: list[str] = Field(default_factory=list)   # 调用了但没预测的

class L4BehaviorResult(ValidationResult):
    """L4 行为反思验证结果（新增）。"""
    predicted_behavior: str = ""     # Agent 自述的预期行为
    actual_behavior: str = ""        # 沙箱实际执行结果
    behavior_match: bool = True      # 行为是否匹配
    behavior_diff: str = ""          # 不匹配时的差异描述

class L5ContractResult(L5ValidationResult):
    """L5 合约反思验证结果（扩展现有）。"""
    self_claimed_contract: str = ""          # Agent 自述的契约
    z3_verified_contract: str = ""           # Z3 实际验证的契约
    contract_mismatch: bool = False          # 自述 vs 实际是否矛盾
```

### 2.2 调度器配置新增常量

```python
# scheduler/task_runner.py — 新增常量

TOOL_TIMEOUT_SECONDS = 20        # 单个工具调用硬超时
ACTION_DEBOUNCE_MS = 0.12        # 动作间防抖延迟（120ms）
MAX_AGENT_CYCLES = 50            # Agent 循环硬上限
```

### 2.3 GraphNode 扩展

```python
# scheduler/graph.py — GraphNode 新增字段

@dataclass
class GraphNode:
    # ... 现有字段 ...
    serialize_tools: bool = False  # True → 此节点禁用并行工具调用
```

## 3. 数据流

### 3.1 US1 — 增强后 Agent 循环

```
TaskRunner.run_task()
  │
  ├─ cycle_count = 0
  │
  └─ while state not in TERMINAL_STATES:
       │
       ├─ cycle_count += 1
       ├─ if cycle_count > MAX_AGENT_CYCLES:          ← 新增：循环上限
       │     state = FAILED
       │     audit.log("max_cycles_exceeded")
       │     break
       │
       ├─ observation = await _agent_cycle(...)        ← 现有
       │
       ├─ if state == CODING:                          ← 新增：CODING 串行化
       │     context["parallel_tool_calls"] = False
       │
       ├─ if needs_debounce(state, prev_state):        ← 新增：防抖延迟
       │     await asyncio.sleep(ACTION_DEBOUNCE_MS)
       │
       ├─ state = _transition(state, fast_lane)        ← 现有
       └─ await _save_checkpoint(...)                  ← 现有

_run_agent():
  │
  └─ try:
       output = await asyncio.wait_for(
           agent.execute(agent_input),
           timeout=TOOL_TIMEOUT_SECONDS                ← 改：从 300s → 20s 工具级超时
       )
     except TimeoutError:
       raise ToolTimeoutError(role, TOOL_TIMEOUT_SECONDS)
```

### 3.2 US2 — 反思式 CoT 增强后验证流

```
L2 反思式验证:
  Agent 生成代码
    │
    ├─ Step 1: 提取 Agent 自述——"此代码将调用 foo(), bar()"  ← 新增
    │
    ├─ Step 2: 沙箱执行 + sys.settrace 追踪                 ← 现有
    │
    ├─ Step 3: 对比 predicted_calls vs actual_calls          ← 新增
    │     deviation = |unexpected| / max(|predicted|, 1)
    │
    └─ Step 4: if deviation > 0.3 → passed=False, warnings    ← 新增

L4 反思式验证:
  Agent 生成代码
    │
    ├─ Step 1: 提取 Agent 自述行为——"此代码接受 int 返回 str" ← 新增
    │
    ├─ Step 2: mypy --strict 静态检查                         ← 现有
    │
    ├─ Step 3: 对比自述类型 vs mypy 推断类型                  ← 新增
    │     不匹配 → behavior_match=False
    │
    └─ Step 4: 结果写 L4BehaviorResult                        ← 新增

L5 反思式验证:
  Agent 生成代码（含 @formal 装饰器）
    │
    ├─ Step 1: 提取 Agent 自述契约——"保证 result > 0"        ← 新增
    │     （从 @ensures 或自然语言注释中提取）
    │
    ├─ Step 2: Z3 形式化验证                                  ← 现有
    │
    ├─ Step 3: 对比 self_claimed_contract vs z3_verified_contract  ← 新增
    │     矛盾 → contract_mismatch=True
    │
    └─ Step 4: 结果写 L5ContractResult                        ← 新增
```

## 4. 调度器状态变更

**无新增状态。** 改动在现有状态机内：

| 改动 | 影响的状态 |
|------|-----------|
| 循环上限触发 | 任何状态 → FAILED（新增转换路径） |
| 工具超时 | CODING、VERIFYING（已有超时 300s 改 20s 工具级） |
| 串行化标志 | CODING（`parallel_tool_calls` 强制 false） |
| 防抖延迟 | CODING→VERIFYING 转换间插入 |

## 5. 防幻觉层影响

| 层 | 改动类型 | 判定逻辑变化 | 误报风险 | 漏报风险 |
|----|---------|-------------|:--:|:--:|
| L2 | 增强 | 原有"函数存在性"验证 + 新增"预测匹配度"验证 | 低（偏差阈值可调） | ↓ 降低（Agent 自述不匹配→新信号） |
| L4 | 增强 | 原有 mypy 类型检查 + 新增"自述类型 vs 实际类型"对比 | 低（仅对比，不改变 mypy 判定） | → 不变（mypy 逻辑不改） |
| L5 | 增强 | 原有 Z3 求解 + 新增"自述契约 vs Z3 契约"对比 | 低（仅标记 mismatch，不阻断） | ↓ 降低（自述契约矛盾→新信号） |

**核心原则**：反思式 CoT 只**增加信号**，不改变现有判定逻辑。`passed` 仍由原有验证决定，反思对比作为 `warnings` / `metadata` 附加。

## 6. 边界 Case 清单

| # | 场景 | 预期行为 |
|---|------|---------|
| B1 | Agent 循环在 49 轮时正常完成 | 正常 DONE，无告警 |
| B2 | Agent 循环达到 50 轮仍未完成 | 强制 FAILED，audit 记录 `max_cycles_exceeded`，保存 checkpoint |
| B3 | 工具调用在 19.5s 时返回 | 正常处理 |
| B4 | 工具调用在 20s 时超时 | 抛 `ToolTimeoutError`，audit 记录，状态转 FAILED |
| B5 | CODING 状态连续写 3 个文件 | 串行执行——写文件1→延迟120ms→写文件2→延迟120ms→写文件3 |
| B6 | Agent 自述调用 `[foo, bar]`，实际调用 `[foo, baz]` | L2 deviation=0.5，passed 仍由原有逻辑决定，warnings 附加偏差信息 |
| B7 | Agent 未提供自述预测（prompt 未生成预测段） | L2 predicted_calls=[]，跳过偏差计算，warnings=["no prediction provided"] |
| B8 | Agent 自述"返回 int"，mypy 推断返回 str | L4 behavior_match=False，behavior_diff 记录类型差异 |
| B9 | Agent 自述契约与 Z3 验证契约完全一致 | L5 contract_mismatch=False，正常通过 |
| B10 | Agent 自述契约"result > 0"但 Z3 找到反例 result=-1 | L5 contract_mismatch=True，z3_status=sat，counterexample 含反例 |
| B11 | L4 的 mypy 不可用 | 跳过 L4 验证（现有逻辑），behavior 对比也跳过 |
| B12 | L5 的 Z3 不可用 | 跳过 L5 验证（现有逻辑），contract 对比也跳过 |

## 7. 风险与缓解

| # | 风险 | 严重度 | 缓解 |
|---|------|:--:|------|
| R1 | 工具超时 20s 过短——复杂代码生成/沙箱执行超 20s | 中 | 超时值可配置（`TOOL_TIMEOUT_SECONDS` 环境变量），CODING 状态用 60s 而非 20s |
| R2 | 循环上限 50 轮太低——大型任务需要更多轮次 | 低 | 可配置（`MAX_AGENT_CYCLES` 环境变量），默认 50 |
| R3 | 反思式 CoT prompt 增加 LLM token 消耗 | 中 | 预测段≤200 tokens，仅在 Test/Prod 启用 L2（已有 `skip_if_empty` 门禁） |
| R4 | Agent 自述预测格式不标准——解析失败 | 中 | 解析失败时 `predicted_calls=[]`，不阻断，fail-open |
| R5 | 现有测试依赖旧行为（无超时/无循环上限） | 低 | 新行为仅在新增参数激活时生效，默认保持兼容 |

## 8. 依赖链

```
scheduler/task_runner.py
  ├── scheduler/graph.py          (GraphNode.serialize_tools 新增)
  ├── observability/audit.py      (audit 日志——已有，只调用)
  └── checkpoint/manager.py       (检查点——已有，只调用)

hallucination/l2_dynamic.py
  ├── hallucination/schemas.py    (L2ReflectionResult 新增)
  └── sandbox/executor.py         (沙箱——已有，只调用)

hallucination/l4_type.py
  └── hallucination/schemas.py    (L4BehaviorResult 新增)

hallucination/l5_z3.py
  └── hallucination/schemas.py    (L5ContractResult 扩展)
```

**无新外部依赖。** 所有改动在现有模块内扩展。

## 9. PRD 对照表

| 验收标准 | 技术方案覆盖 | 实现位置 |
|---------|------------|---------|
| AC1 工具级超时 | §3.1 `_run_agent` 超时 20s + `ToolTimeoutError` | `task_runner.py` |
| AC2 CODING 串行化 | §2.3 `GraphNode.serialize_tools` + §3.1 `parallel_tool_calls=False` | `task_runner.py` + `graph.py` |
| AC3 循环上限 50 轮 | §3.1 `cycle_count > MAX_AGENT_CYCLES → FAILED` | `task_runner.py` |
| AC4 防抖延迟 120ms | §3.1 `asyncio.sleep(ACTION_DEBOUNCE_MS)` | `task_runner.py` |
| AC5 L2 预测字段 | §2.1 `L2ReflectionResult` + §3.2 L2 反思流 | `schemas.py` + `l2_dynamic.py` |
| AC6 L4 行为对比 | §2.1 `L4BehaviorResult` + §3.2 L4 反思流 | `schemas.py` + `l4_type.py` |
| AC7 L5 契约对比 | §2.1 `L5ContractResult` + §3.2 L5 反思流 | `schemas.py` + `l5_z3.py` |
| AC8 现有测试全通过 | §5 不改变现有判定逻辑，反思作为附加信号 | 全部改动文件 |

---

> 覆盖 8/8 条验收标准，无偏离。
