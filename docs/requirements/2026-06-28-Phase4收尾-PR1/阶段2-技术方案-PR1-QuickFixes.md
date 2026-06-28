# PR #1 Quick Fixes — 阶段2 技术方案

> 基线: 阶段1-PRD-PR1-QuickFixes.md | 日期: 2026-06-28

## PRD 对照

| AC | 方案 | 状态 |
|----|------|:--:|
| `.gitignore` 含 `.orbit/` | 末尾加 `# Orbit runtime` + `.orbit/` | ✅ |
| `git ls-files .orbit/` 空 | `git rm --cached .orbit/memory/MEMORY.md` | ✅ |
| 单处 startup handler | 移除 module 级 `_start_watchdog`，合并到 factory 内 startup | ✅ |
| wt_record None 检查 | `if wt_record is not None:` 包裹 logger.info (line 83-87) | ✅ |
| execute_stream finally | `try:` 在 setup 后，`finally:` 在 generator 末尾 | ✅ |

## 改动详情

### 1. `.gitignore`
```
+ # Orbit runtime
+ .orbit/
```

### 2. `main.py`
- 删除 line 190-196（module 级 `@app.on_event("startup")` + `_start_watchdog`）
- 在 factory 内 startup handler（line 115）中加入 `asyncio.create_task(_actor_watchdog.run())`
- `_actor_watchdog` 在 line 168 已定义，factory 内可直接引用（闭包）

### 3. `orchestrator.py`
- Line 82 后换为：
```python
wt_record = await self._worktree.create(...)
if wt_record is not None:
    logger.info("compose_worktree_created", id=..., branch=...)
```

### 4. `react_agent.py`
- Line 179（setup 完成）后加 `try:`
- Line 472（MAX_TURNS yield）后加 finally 块：
```python
finally:
    logger.debug("execute_stream_cleanup", task_id=task_id)
    if cancel_token and not cancel_token.is_cancelled:
        cancel_token.cancel()
```

## 风险

无。4 项均为增/删 ≤5 行的外科手术式改动。
