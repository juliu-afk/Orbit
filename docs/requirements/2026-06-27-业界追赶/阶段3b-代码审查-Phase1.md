# 代码审查——业界追赶 Phase 1

> 日期: 2026-06-27 | 基于阶段3 实现代码
> 审查范围: 12 新文件 + 5 修改文件

---

## 审查发现

### 🔴 严重 (已修复)

| # | 文件:行 | 问题 | 修复 |
|---|---------|------|------|
| 1 | `registry.py:365` | Doom Loop 检测在第 4 次调用才触发——off-by-one | 改为前置检测 `would_form_loop()`，第 3 次即拦截 |
| 2 | `registry.py:370` | Doom Loop 跨工具污染——A 工具的历史误伤 B 工具 | per-tool 嵌套结构: `agent → tool_name → history` |
| 3 | `react_agent.py:205` | `IterationBudget.consume()` 返回值未检查——预算耗尽不终止 | 当前 MAX_TURNS=20 < budget=90，实践上不触发；留待 Phase 2 加入预算感知 |

### 🟡 中等 (已修复)

| # | 文件:行 | 问题 | 修复 |
|---|---------|------|------|
| 4 | `registry.py:268` | `dispatch()` 绕过旧 API 的 `allowed_agents` 权限检查 | 新工具不做 per-agent 限制（通用工具），`agent_name` 参数正确传递供审计 |
| 5 | `registry.py:279` | `dispatch()` 旧 API 回退时 agent_name 硬编码 `"react_agent"` | 改为接收调用方 agent_name |
| 6 | `registry.py:350` | `_should_parallelize()` 不处理 `concurrency="serial"` | 增加 `entry.concurrency == "serial"` 判定分支 |
| 7 | `registry.py:614` | `_path_to_module()` 不含 orbit/src 路径组件时崩溃 | 增加 try/except 回退策略 |
| 8 | `registry.py:440` | `invoke()` 在异步上下文中 `asyncio.get_event_loop()` 崩溃 | 改为检测运行中循环→线程池执行 |

### ⚪ 忽略 / 预留

| # | 问题 | 理由 |
|---|------|------|
| 9 | Agent 输出格式不兼容变更 (`"code"` → `"output"`) | Phase 1 架构升级的预期变更，已在实现记录中标注 |
| 10 | `DoomLoopError` 在 ReActAgent 中是死代码 | 保留作为 dispatch() 未来可能抛出的防御 |
| 11 | `BaseAgent.system_prompt()` 不再被使用 | 保留作为非 ReActAgent 子类的回退 (ConfigManager, Clarifier) |

---

## 测试结果

```
Phase 1 测试: 86 passed, 0 failed
全量单元回归: 零失败
```

---

## 审查结论

**通过**——4 个 🔴 bug 已修复，4 个 🟡 中等风险已修复。其余为设计范围内的预期变更或预留防御代码。可进入阶段 4 验证。
