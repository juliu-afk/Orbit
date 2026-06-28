# PR #4 Frontend + Tests — 阶段2 技术方案

> 基线: 阶段1-PRD-PR4-FrontendTests.md

## Issue 7: ChatStream.vue

### 新建文件
1. **`frontend/src/types/stream.ts`** — StreamEventType 枚举（匹配后端 `StreamEventType`）
2. **`frontend/src/composables/useEventSource.ts`** — SSE composable（参考 `useWebSocket.ts` 模式）
3. **`frontend/src/components/chat/ChatStream.vue`** — 流式输出 UI 组件

### 数据流
```
ChatStream.vue → POST /api/v1/agent/{agentId}/run → taskId
              → new EventSource(/api/v1/agent/{agentId}/stream?taskId=...)
              → 按 event type 分发渲染
              → 取消: POST /api/v1/agent/{agentId}/cancel
```

### UI 渲染
- `text_delta` → 累积文本追加到消息区
- `thinking` → 闪烁指示器 "Agent 思考中..."
- `tool_call` → 工具调用卡片（名称+参数）
- `tool_result` → 工具结果折叠区
- `finish_step` → 完成标记 + emit('finish')
- `error` → 错误提示

## Issue 11: WorktreeManager 测试

### 修改文件
**`tests/unit/test_worktree.py`** — 加 10-15 测试

### 新增测试

| # | 测试 | 覆盖目标 |
|---|------|---------|
| 1 | `_git()` 成功 | subprocess 正常返回 stdout |
| 2 | `_git()` 非零退出 | RuntimeError 传播 |
| 3 | `_git()` stderr | 错误消息含 stderr |
| 4 | `create()` git 失败 | 异常处理 + 清理 |
| 5 | `create()` 非常规 base_branch | 分支命名 |
| 6 | `resolve()` ASK 策略 | ASK→MERGED dispatch |
| 7 | `resolve()` ASK 策略 DISMISS | ASK→DISMISSED dispatch |
| 8 | `_cleanup()` git 失败 | RuntimeError |
| 9 | `cleanup_safe()` 部分失败 | 其他记录不受影响 |
| 10 | 并发 create() | 两记录不同 ID |

### FakeProc 模式
```python
class FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
    async def communicate(self): return (self._stdout, self._stderr)
```

Mock: `monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)`
