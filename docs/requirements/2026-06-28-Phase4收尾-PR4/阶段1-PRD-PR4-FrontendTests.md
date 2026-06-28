# PR #4 Frontend + Tests — 阶段1 PRD

> 日期: 2026-06-28 | 分支: feat/phase4-frontend-tests

## 背景

Phase 4 收尾最后两个缺口：
1. SSE 流式端点已可用，前端缺少消费组件
2. WorktreeManager 测试覆盖率 ~20%，核心模块 `_git()` subprocess 层完全未测

## 用户故事

| # | P | 描述 | AC |
|---|:--:|------|-----|
| 7 | P1 | 用户在 Chat 页面看到 Agent 流式输出 | ChatStream.vue 显示 text_delta/thinking/tool_call/tool_result/finish_step |
| 11 | P1 | WorktreeManager 关键代码路径有测试覆盖 | +10-15 测试，覆盖率 ≥80% |

## Non-Goals

- 不做 SSE 端点功能增强（已实现）
- 不做 Redis 分布式锁测试（non-goal）
