# PR #3 Backend Features — 阶段1 PRD

> 日期: 2026-06-28 | 分支: feat/phase4-backend-features

## 背景

3 个后端功能缺口：/dream 未暴露 HTTP 入口、Compose 无限流、PermissionEngine 无审计。

## 用户故事

| # | P | 描述 | AC |
|---|:--:|------|-----|
| 6 | P0 | /dream 端点可调用 | POST /api/v1/dream/run 触发 5 阶段循环，GET /dream/status 查状态 |
| 9 | P1 | Compose 端点防滥用 | >5 req/60s → 429 Too Many Requests |
| 10 | P1 | 权限拒绝可审计 | PermissionEngine.check() deny → AuditLogger.log() |

## Non-Goals

- 不做 DreamEngine 功能增强（已实现）
- 不做 Redis 分布式限流（MVP 内存限流）
- 不改 permission check 逻辑（只加日志）
