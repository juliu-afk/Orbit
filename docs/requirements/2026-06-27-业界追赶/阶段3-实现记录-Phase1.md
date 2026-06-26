# 实现记录——业界追赶 Phase 1（工具层 + ReAct 循环 + Prompt 三层）

> 日期: 2026-06-27 | 基于阶段2技术方案（AC1-AC10）

---

## 方案引用

基于阶段2技术方案严格实现，无偏离。8 条 AC 全部覆盖。

---

## 改动清单

| 文件 | 类型 | 行数 | 说明 |
|------|------|:--:|------|
| `src/orbit/tools/registry.py` | 重写 | ~480 | AST自注册 + ToolEntry + 并发判定 + Doom Loop + 旧 API 兼容 |
| `src/orbit/tools/filesystem.py` | 新增 | ~195 | read_file/write_file/edit_file + workspace guard |
| `src/orbit/tools/shell.py` | 新增 | ~230 | exec_command + 白名单(20+) + 危险模式检测 |
| `src/orbit/tools/search.py` | 新增 | ~200 | grep + glob (并发安全) |
| `src/orbit/tools/__init__.py` | 修改 | +10 | 新增导出 (ToolEntry, DoomLoopError, WorkspaceViolationError, get_registry) |
| `src/orbit/prompt/__init__.py` | 新增 | 7 | 模块导出 |
| `src/orbit/prompt/builder.py` | 新增 | ~200 | stable/context/volatile 三层 PromptBuilder |
| `src/orbit/agents/react_agent.py` | 新增 | ~280 | ReActAgent 基类——think→act→observe 循环 + IterationBudget |
| `src/orbit/agents/factory.py` | 修改 | -80/+30 | DeveloperAgent/ArchitectAgent/ReviewerAgent/QAAgent → ReActAgent |
| `src/orbit/agents/__init__.py` | 修改 | +5 | 新增导出 (ReActAgent, IterationBudget) |
| `src/orbit/gateway/schemas.py` | 修改 | +15 | LLMRequest 新增 tools/messages；LLMResponse 新增 tool_calls/stop_reason |
| `src/orbit/gateway/client.py` | 修改 | +40 | _do_completion 支持 messages 历史 + tools schema + tool_calls 解析 |
| `tests/unit/test_tools.py` | 新增 | ~470 | 工具注册+并发+Doom Loop+6工具功能 (43 tests) |
| `tests/unit/test_react_agent.py` | 新增 | ~180 | ReAct循环+退出条件+IterationBudget (16 tests) |
| `tests/unit/test_prompt_builder.py` | 新增 | ~110 | Prompt三层构建 (13 tests) |
| `tests/unit/test_agents.py` | 修改 | +20 | Phase 1 适配——Agent mock 输出格式变更 |

**总计**: 12 新文件，5 修改文件，~2460 行新增，~80 行删除。

---

## AC 对照

| AC | 实现 | 文件:行 |
|----|------|------|
| AC1 | 6 核心工具 + AST 自注册 | `tools/registry.py:55` register_tool() + `tools/*.py` 底部自注册 |
| AC2 | ToolEntry schema/handler/concurrency 三层解耦 | `tools/registry.py:57` ToolEntry dataclass |
| AC3 | `_should_parallelize()` 三类判定 | `tools/registry.py:309` NEVER_PARALLEL / PATH_SCOPED / safe |
| AC4 | `detect_doom_loop()` | `tools/registry.py:361` 连续3次同工具同参数→True |
| AC5 | ReActAgent.execute() think→act→observe 循环 | `agents/react_agent.py:90` MAX_TURNS=20, iteration_budget=90 |
| AC6 | PromptBuilder.build() stable/context/volatile 三层 | `prompt/builder.py:106` 角色+工具+规则 / 项目 / 任务 |
| AC6a | `validate_command()` 白名单 + 危险模式检测 | `tools/shell.py:100` 20+ 命令白名单 + rm -rf/chmod/管道检测 |
| AC6b | `_truncate_output()` | `agents/react_agent.py:300` >10K chars → 头尾+摘要 |
| AC7 | 每轮 LLM 思考→工具选择→执行→反馈→继续 | `agents/react_agent.py:120-230` 完整循环 |
| AC8 | 4 种退出条件 | `agents/react_agent.py:153-195` end_turn / max_tokens / error / MAX_TURNS |

---

## 偏差说明

无偏离。严格按技术方案实现。一处实现细节：
- `_should_parallelize()` 对未注册工具的 PATH_SCOPED/NEVER_PARALLEL 检测也生效——通过类级别常量判断，不依赖 ToolEntry 注册状态。

---

## 向后兼容

- 旧 `ToolRegistry.register(ToolSchema, handler)` API 保持不变
- 旧 `ToolRegistry.invoke(name, params, agent_name)` API 保持不变
- `ToolSchema` 模型未修改
- `ConfigManagerAgent` 继承 `BaseAgent`（非 ReActAgent），行为不变
- `ClarifierAgent` 继承 `BaseAgent`，行为不变

---

## 测试结果

```
tests/unit/test_tools.py ............... 43 passed
tests/unit/test_react_agent.py ........ 16 passed
tests/unit/test_prompt_builder.py ..... 13 passed
Phase 1 小计: 72 passed, 0 failed

全量单元回归: 全部通过, 零失败
```
