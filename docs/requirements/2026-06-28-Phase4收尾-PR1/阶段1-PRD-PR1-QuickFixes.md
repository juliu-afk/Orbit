# PR #1 Quick Fixes — 阶段1 PRD

> 日期: 2026-06-28 | 分支: fix/phase4-quick-fixes | 参考: 总结-业界追赶.md §6

## 背景

Phase 4 业界追赶收尾后 code review 发现 4 个低风险代码质量问题。

## 用户故事

| # | 优先级 | 描述 | AC |
|---|:--:|------|-----|
| 1 | P0 | `.orbit/` 运行时数据不应进 git | `.gitignore` 含 `.orbit/`，`git ls-files .orbit/` 空 |
| 2 | P1 | startup handler 不应分散两处 | 单处 `@app.on_event("startup")` 启动所有后台任务 |
| 4 | P1 | `wt_record` None 访问需显式防护 | orchestrator line 85-86 在 None check 内访问属性 |
| 8 | P1 | `execute_stream` generator 需 finally 清理 | 所有退出路径触发 finally，log 包含 task_id |

## Non-Goals

- 不改为 FastAPI lifespan（范围外，保持最小 diff）
- 不重构 execute_stream 控制流（只加 try/finally 壳）
- 不动 line 127 的 wt_record 安全访问（已正确）

## 待确认

无——4 项均为明确 bug/code smell，无需额外澄清。
