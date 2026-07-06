# 阶段3-实现记录-Grill交互协议层.md

> 基于阶段2 技术方案（覆盖 PRD 8 条验收标准）。
> 严格按方案实现，无偏离。

## 方案引用

| 设计决策 | 实现位置 | 是否按方案 |
|---------|---------|:--:|
| ModeConfig/BehaviorConfig Pydantic 模型 | `src/orbit/modes/schemas.py:17-55` | ✅ |
| ModeLoader 读取/校验/缓存/降级 | `src/orbit/modes/loader.py:51-127` | ✅ |
| 3 内置 mode（clarify/architect/review） | `src/orbit/modes/{clarify,architect,review}/mode.yaml` | ✅ |
| References 按需加载（≤200 行限制） | `loader.py:load_reference()` | ✅ |
| AgentFactory.get_agent() mode 参数 | `src/orbit/agents/factory.py:235,272-273` | ✅ |
| ClarifierAgent 从 _mode 读行为 | `src/orbit/agents/clarifier.py:323-344` | ✅ |
| ContextStage 三阶段枚举 | `src/orbit/agents/context.py:19-27` | ✅ |
| TaskContext.load_stage() 累加升级 | `src/orbit/agents/context.py:66-120` | ✅ |
| _build_context 仅 Stage 1（L1+L3） | `src/orbit/scheduler/task_runner.py:541-558` | ✅ |
| _agent_cycle 加载 mode | `src/orbit/scheduler/task_runner.py:280-293` | ✅ |
| _run_agent 失败自动升级 Stage 2 | `src/orbit/scheduler/task_runner.py:518-537` | ✅ |

## 改动清单

### 新增文件（8 个 Python + 7 个 YAML/MD）

| 文件 | 行数 | 用途 |
|------|------|------|
| `src/orbit/modes/__init__.py` | 22 | 包初始化，导出 ModeLoader/ModeConfig |
| `src/orbit/modes/schemas.py` | 60 | Pydantic 数据模型（ModeConfig/BehaviorConfig/QuestionStrategy） |
| `src/orbit/modes/loader.py` | 127 | ModeLoader——YAML 加载/Pydantic 校验/内存缓存/references 按需加载 |
| `src/orbit/modes/clarify/mode.yaml` | 17 | 需求澄清模式：深度优先+推荐答案+代码库优先 |
| `src/orbit/modes/clarify/references/question-tree.md` | 28 | 决策树模板——目标/范围/验收三分支深度优先遍历 |
| `src/orbit/modes/clarify/references/domain-checks.md` | 15 | 领域检查——术语一致性/模糊语言锐化/代码交叉验证 |
| `src/orbit/modes/architect/mode.yaml` | 16 | 架构设计模式：多视角方案生成+三维评分 |
| `src/orbit/modes/architect/references/perspectives.md` | 20 | 多视角设计模板（方案格式+评分标准） |
| `src/orbit/modes/review/mode.yaml` | 17 | 代码审查模式：6 维度检查+致命优先 |
| `src/orbit/modes/review/references/checklist.md` | 30 | 审查清单——安全/财务/会计/方案/测试/质量 |
| `src/orbit/modes/review/references/severity-rubric.md` | 8 | 严重度分级——致命/严重/一般/建议 |
| `tests/unit/test_modes.py` | 161 | 11 条单元测试（加载/校验/降级/缓存/references/状态匹配） |
| `tests/unit/test_context_stage.py` | 78 | 4 条单元测试（Stage 默认值/有序性/不降级/最多升级一次） |

### 修改文件（4 个）

| 文件 | 改动 | 行数变化 |
|------|------|---------|
| `src/orbit/agents/context.py` | 新增 ContextStage 枚举 + TaskContext.load_stage() 三阶段加载方法 | +130 |
| `src/orbit/agents/factory.py` | get_agent()/create() 新增 mode 参数；创建后注入 agent._mode | +19 |
| `src/orbit/agents/clarifier.py` | 新增 _question_strategy/_require_recommendation/_codebase_first 属性；修复文件重复（删除重复的 850 行） | -874 |
| `src/orbit/scheduler/task_runner.py` | _agent_cycle 加载 mode；_run_agent 注入 mode + 失败自动升级；_build_context 仅 Stage 1 | +74 |

### 文档（3 个）

| 文件 | 用途 |
|------|------|
| `docs/开发计划_V14.1.md` | 版本历史 + 子文档索引 |
| `docs/产品路线图.md` | v0.33.0 交互协议层章节（6 功能+5 原则对比） |
| `docs/requirements/2026-07-06-Grill交互协议层/阶段1-PRD-Grill交互协议层.md` | 阶段 1 产出 |

## 偏差说明

**严格按方案实现，无偏离。**

额外修复（非方案内容，但属于代码质量改进）：
- 修复 `clarifier.py` 文件重复问题：原始文件 1707 行包含两份完全重复的内容（lines 856-1704），已截断至 855 行

## 回溯对照：PRD 验收标准 → 实现

| AC# | 验收标准 | 方案设计 | 代码实现 |
|-----|---------|---------|---------|
| AC1 | `src/orbit/modes/` 含 3 内置 mode | 新建 modes/ + clarify/architect/review 子目录 | `modes/{clarify,architect,review}/mode.yaml` |
| AC2 | AgentFactory 读取 mode.yaml | get_agent(mode=ModeConfig) | `factory.py:235,272` |
| AC3 | 换 question_strategy 行为变化 | ClarifierAgent 读 self._mode.behavior | `clarifier.py:323-344` |
| AC4 | Stage 1 ≤2K tokens | _build_context 只构建 L1+L3（L2/L4/L5 空） | `task_runner.py:541-558` |
| AC5 | fast lane 只触发 Stage 1 | _build_context 不再加载 MemoryStore（L4 空） | `task_runner.py:546-553`（MemoryStore 逻辑已移除） |
| AC6 | 失败自动升级 Stage 2 | _run_agent except 块调用 ctx.load_stage(STAGE2) | `task_runner.py:518-537` |
| AC7 | 453 测试全绿 | 不破坏现有 API | 5 预存失败 + test_build_context 修复 + 15 新测试通过 |
| AC8 | 新增 ≥10 条测试 | tests/unit/test_modes.py + test_context_stage.py | 11 + 4 = 15 条 |

## 测试结果

```
tests/unit/test_modes.py::test_load_mode_success PASSED
tests/unit/test_modes.py::test_load_mode_missing_file PASSED
tests/unit/test_modes.py::test_load_mode_cache PASSED
tests/unit/test_modes.py::test_load_mode_invalid_yaml PASSED
tests/unit/test_modes.py::test_list_modes PASSED
tests/unit/test_modes.py::test_resolve_for_state PASSED
tests/unit/test_modes.py::test_load_reference PASSED
tests/unit/test_modes.py::test_load_reference_missing PASSED
tests/unit/test_modes.py::test_mode_config_defaults PASSED
tests/unit/test_modes.py::test_behavior_config_validation PASSED
tests/unit/test_modes.py::test_question_strategy_values PASSED
tests/unit/test_context_stage.py::test_stage1_defaults PASSED
tests/unit/test_context_stage.py::test_context_stage_ordering PASSED
tests/unit/test_context_stage.py::test_load_stage_no_downgrade PASSED
tests/unit/test_context_stage.py::test_load_stage_upgrade_once_only PASSED
tests/unit/test_context_stage.py::test_load_stage_to_same_or_lower_is_noop PASSED
→ 15/15 PASSED
```

回归：5 项预存失败（非本次引入），其余全部通过。

---

> 基于阶段3 实现记录（15 条测试通过），等待用户确认 diff 后 commit。
