# PR #3 Backend Features — 阶段2 技术方案

> 基线: 阶段1-PRD-PR3-BackendFeatures.md

## PRD 对照

| AC | 方案 |
|----|------|
| POST /dream/run | 新建 `dream.py` router，注入 `app.state.dream_engine` |
| GET /dream/status | 同上 router，返回引擎状态 |
| 429 on >5 req/60s | 新建 `RateLimiter` 类（deque 滑动窗口），Depends 注入 compose |
| deny → AuditLogger | permission.py 4 处 deny + 1 处 grant → AuditLogger.log() |

## 改动详情

### Issue 6: dream 端点
- **新建** `src/orbit/api/routes/dream.py`：POST `/dream/run` + GET `/dream/status`
- **修改** `src/orbit/api/main.py`：import + register + inject DreamEngine
- DreamEngine 无 LLM 也能跑（纯文本合并），不需要 LLMClient 参数

### Issue 9: rate limiting
- **新建** `src/orbit/api/middleware/rate_limit.py`：`RateLimiter` 类
  - 算法：deque 滑动窗口（复用 `tools/registry.py:594` 模式）
  - Key：`client_ip:path`
  - 限额：5 req/60s for compose
  - 返回 429 + `Retry-After` header
- **修改** `src/orbit/api/routes/compose.py`：加 `_: None = Depends(_compose_limiter)`

### Issue 10: audit log
- **修改** `src/orbit/security/permission.py`：
  - import AuditLogger
  - 4 处 `logger.warning("permission_denied",...)` → 追加 `_audit.log(component="permission_engine", operation="deny_*", status="denied", ...)`
  - 1 处 return True（line 133）前 → 追加 `_audit.log(..., status="allowed")`
  - 保留 logger.warning（运维告警），追加 AuditLogger（审计留痕）

## 数据流

```
POST /dream/run → DreamEngine.run() → 5 stage → DreamResult → JSON response
POST /compose/run → RateLimiter → ComposeOrchestrator.run_spec()
PermissionEngine.check() → AuditLogger.log() → return bool
```

## 风险

- DreamEngine 无 LLM 时 stage 2-3 返回原文（`.run()` 有 fallback）
- Rate limiter 内存存储，重启清零——MVP 可接受
