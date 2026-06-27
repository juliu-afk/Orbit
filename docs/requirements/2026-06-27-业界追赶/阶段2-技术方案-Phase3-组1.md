# 技术方案——Phase 3 组 1：流式 + Schema 标准化（AC18-AC19）

> 日期: 2026-06-27 | 基于 `阶段1-PRD-Phase3.md` 组 1 验收标准
> 依赖: 现有 react_agent.py / gateway/ / ws/ / events/

---

## 1. PRD 对照表

| AC | 标准 | 技术方案覆盖 |
|----|------|------------|
| AC19.1 | 流式事件: text-delta/tool-call/finish-step/error | `StreamEvent` 4 类型 + `execute_stream()` async generator |
| AC19.2 | ReActAgent → async generator | `ReActAgent.execute_stream()` 新方法，`execute()` 保留为 wrapper |
| AC19.3 | CancellationToken + cleanup | `CancellationToken` 类 + finally 块 |
| AC19.4 | SSE 端点 `/api/v1/agent/{id}/stream` | FastAPI `StreamingResponse` + SSE 格式 |
| AC19.5 | 流式中断 | 驾驶舱发送 cancel → API 调用 `token.cancel()` → Agent 下轮检查 |
| AC18.1 | ProviderAdapter base | `ProviderAdapter` ABC: `normalize_tool_schema()` / `normalize_response()` |
| AC18.2 | Anthropic + OpenAI adapter | `AnthropicAdapter` / `OpenAIAdapter`（Gemini later） |
| AC18.3 | LLM provider 路由增强 | `RoutingStrategy` 枚举 + `LLMClient.generate()` 集成 |

无偏离。

---

## 2. 数据模型

### 2.1 StreamEvent（新文件 `src/orbit/stream/events.py`）

```python
from enum import StrEnum
from pydantic import BaseModel, Field

class StreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"       # LLM 逐 token 输出
    TOOL_CALL = "tool_call"         # Agent 调用工具
    TOOL_RESULT = "tool_result"     # 工具执行结果
    TURN_START = "turn_start"       # 新一轮思考
    FINISH_STEP = "finish_step"     # Agent 完成一步（可用于 checkpoint）
    ERROR = "error"                 # 错误

class StreamEvent(BaseModel):
    type: StreamEventType
    agent_id: str
    task_id: str
    turn: int = 0
    data: dict = Field(default_factory=dict)
    # type=text_delta:  data={"delta": "some text"}
    # type=tool_call:   data={"tool": "read_file", "args": {...}}
    # type=tool_result: data={"tool": "read_file", "result_size": 1024, "truncated": false}
    # type=turn_start:  data={"turn": 3, "remaining": 17}
    # type=finish_step: data={"output": "...", "turns": 5, "tool_calls": 12}
    # type=error:       data={"message": "...", "code": "MAX_TURNS"}
```

### 2.2 CancellationToken（新文件 `src/orbit/stream/cancellation.py`）

```python
import asyncio

class CancellationToken:
    """轻量取消令牌——对标 OpenClaw wrapToolWithAbortSignal."""
    def __init__(self):
        self._cancelled = False
        self._event = asyncio.Event()
    def cancel(self): self._cancelled = True; self._event.set()
    @property
    def is_cancelled(self) -> bool: return self._cancelled
    async def wait_if_cancelled(self): ...
```

### 2.3 RoutingStrategy（新文件 `src/orbit/gateway/routing.py`）

```python
from enum import StrEnum

class RoutingStrategy(StrEnum):
    CHEAPEST = "cheapest"     # 成本最低（GLM-4.7 Flash）
    FASTEST = "fastest"       # 延迟最低
    BEST_QUALITY = "best"     # 最强模型（GLM-5.2 / DS V4 Pro）
    AGENT_DEFAULT = "agent"   # 按 Agent 角色默认（现有行为）

class RoutingDecision(BaseModel):
    strategy: RoutingStrategy
    model: str
    reason: str
```

### 2.4 现有模型改动

**LLMRequest**（gateway/schemas.py）加 1 字段：
```python
provider: str | None = None  # "anthropic" | "openai" | None(自动检测)
```

**LLMResponse**（gateway/schemas.py）加 1 字段：
```python
provider_adapter: str | None = None  # 应用的 adapter 名称（审计用）
```

---

## 3. 数据流

### 3.1 流式 Agent 执行（AC19）

```
驾驶舱 SSE connect ──→ POST /api/v1/agent/{id}/run ──→ Orchestrator
                                                           │
                                          AgentFactory.create() → ReActAgent
                                                           │
                                          agent.execute_stream(token) ← async generator
                                                           │
                              ┌─────────────────────────────┤
                              │ yield StreamEvent(type=TURN_START)
                              │ LLMClient.generate_stream() → litellm stream
                              │   yield StreamEvent(type=TEXT_DELTA, data={"delta": t})
                              │   有 tool_calls?
                              │     yield StreamEvent(type=TOOL_CALL, ...)
                              │     result = await tools.dispatch(...)
                              │     yield StreamEvent(type=TOOL_RESULT, ...)
                              │ 检查 token.is_cancelled? → break
                              │ yield StreamEvent(type=FINISH_STEP, ...)
                              └─────────────────────────────┘
                                                           │
                              StreamingResponse(stream) ←──┘
```

### 3.2 Schema 标准化管线（AC18）

```
LLMClient.generate()
  │
  ├─ 1. RoutingStrategy 选模型
  │     cheapest → GLM-4.7 Flash
  │     best     → GLM-5.2 / DS V4 Pro
  │     agent    → 现有 Resolver 逻辑
  │
  ├─ 2. ProviderAdapter.normalize_tool_schema(req.tools)
  │     Anthropic: 无需改动（兼容 OpenAI format）
  │     OpenAI: 直接透传
  │     Gemini: 剥离 minLength/maxLength/pattern/format/const/enum（later）
  │
  ├─ 3. litellm.acompletion(normalized_kwargs)
  │
  └─ 4. ProviderAdapter.normalize_response(raw) → LLMResponse
        Anthropic: stop_reason 映射
        OpenAI: 直接透传
```

---

## 4. API 设计

### 4.1 SSE 端点（新路由 `src/orbit/stream/sse.py`）

```
GET /api/v1/agent/{agent_id}/stream
  → SSE (text/event-stream)

SSE 帧格式:
  event: text_delta
  data: {"agent_id": "...", "task_id": "...", "turn": 3, "data": {"delta": "..."}}

  event: tool_call
  data: {"agent_id": "...", "task_id": "...", "turn": 3, "data": {"tool": "read_file", ...}}

  event: finish_step
  data: {"agent_id": "...", "task_id": "...", "data": {"output": "..."}}

  event: error
  data: {"agent_id": "...", "task_id": "...", "data": {"message": "...", "code": "MAX_TURNS"}}
```

### 4.2 取消端点

```
POST /api/v1/agent/{agent_id}/cancel
  → {"code": 0, "data": {"cancelled": true}, "message": "ok"}

实现: 查找 CancellationToken → token.cancel()
```

### 4.3 Agent 运行端点（启动流式任务）

```
POST /api/v1/agent/{agent_id}/run
  Body: {"task": "...", "role": "developer", "context": {}}
  → {"code": 0, "data": {"task_id": "abc123"}, "message": "ok"}

客户端随后连 GET /api/v1/agent/{agent_id}/stream?task_id=abc123
```

---

## 5. 调度器状态变更

**无状态变更**。ReActAgent 的内部循环从 `async def → async generator` 不影响 Orchestrator 状态机。

Orchestrator 调用变化：
```python
# 旧（组 1 前）
output = await agent.execute(input_data)

# 新（组 1 后）——execute() 保留为兼容 wrapper
output = await agent.execute(input_data)  # 内部调 execute_stream() 收集结果
```

向后兼容：所有现有调用方（orchestrator.py, clarifier.py）无需改动。

---

## 6. 防幻觉层影响

| 层 | 影响 | 处理 |
|---|------|------|
| L1-L8 | 无影响——流式不解包防幻觉判定逻辑 | 不变 |
| L3 熵监控 | 流式逐 token 通过时不可用（logprobs 在 stream 模式下不一样） | 流式模式跳过 L3，`finish_step` 后回放 |
| L7 沙箱 | 无影响——工具执行仍在 Docker | 不变 |

---

## 7. 图谱 Schema 变更

无。

---

## 8. 边界 case 清单

| 场景 | 预期行为 | 对应代码 |
|------|---------|---------|
| LLM 流式中断（网络断开） | `litellm` 抛异常 → `except` 块 yield `StreamEvent(type=ERROR)` → generator 正常结束 | `react_agent.py:_execute_stream_impl` |
| 用户在 turn 3 点击取消 | `CancellationToken.cancel()` → Agent 在 turn 3 LLM 调用前检查 `token.is_cancelled` → yield ERROR + break | `react_agent.py:execute_stream` |
| 流式连接断开但 Agent 仍在跑 | SSE 端检测 `request.is_disconnected()` → token.cancel() → Agent 清理 | `stream/sse.py` |
| Provider schema 不兼容 | `normalize_tool_schema()` 跳过未知字段 → WARN 日志 → 发送 normalized schema | `gateway/adapters/anthropic.py` |
| 旧同步调用方仍调 `execute()` | `execute()` 内部 `async for e in self.execute_stream(...)` 收集结果 → 返回 `AgentOutput` | `react_agent.py:execute` |
| 多个 SSE 客户端同时连同一 task | 每个 SSE 连接独立 iterator，共享同一 CancellationToken（任一取消全部取消） | `stream/sse.py` |
| RoutingStrategy 选 cheapest 但无免费模型 | 回退 default_model（DS V4 Pro） | `gateway/routing.py` |
| adapter normalize 异常 | 返回原始 schema（no-op）+ WARN，不阻断 LLM 调用 | `gateway/adapters/base.py` |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| litellm stream 与现有 `_do_completion` 行为不同 | 不重构 `_do_completion`，新增 `_stream_completion_with_tools()` 独立方法 |
| async generator 内存泄漏 | finally 块确保资源释放（对标 Effect.uninterruptible） |
| SSE vs WebSocket 双通道维护成本 | SSE 用于流式 Agent 输出（单向），WS 保留用于驾驶舱指标推送（双向订阅）。职责不同，不合并 |
| ProviderAdapter 覆盖不全 | base class 默认 no-op，子类只覆盖差异部分。新 provider 加一个 adapter 即可 |
| 流式 token 输出与 tool_calls 解析冲突 | litellm stream 累积 `delta.content`，`finish_reason=tool_calls` 时切换到 tool 解析模式——与 `_do_completion` 逻辑对齐 |

---

## 10. 依赖链

```
src/orbit/stream/events.py          (新) — StreamEvent, StreamEventType
src/orbit/stream/cancellation.py    (新) — CancellationToken
src/orbit/stream/sse.py             (新) — FastAPI SSE 路由
src/orbit/agents/react_agent.py     (改) — execute_stream() async generator
src/orbit/agents/base.py            (改) — AgentOutput 加 stream 字段?
                                         (不改——stream 通过 async generator 传递，不影响模型)
src/orbit/agents/factory.py         (改) — create() 传 cancel_token
src/orbit/gateway/adapters/__init__.py (新) — ProviderAdapter base
src/orbit/gateway/adapters/anthropic.py (新) — AnthropicAdapter
src/orbit/gateway/adapters/openai.py    (新) — OpenAIAdapter
src/orbit/gateway/routing.py        (新) — RoutingStrategy + RoutingDecision
src/orbit/gateway/client.py         (改) — generate() 集成 adapter + routing
src/orbit/gateway/schemas.py        (改) — LLMRequest.provider
src/orbit/main.py                   (改) — 注册 stream router
frontend/src/components/chat/ChatStream.vue (新) — 流式聊天组件
```

外部依赖：零新增。`litellm` 已安装，`asyncio` 标准库。

---

## 11. 文件清单（预估行数）

| 文件 | 类型 | 行数 | 职责 |
|------|------|:--:|------|
| `src/orbit/stream/__init__.py` | 新 | 10 | 模块导出 |
| `src/orbit/stream/events.py` | 新 | ~50 | StreamEvent + StreamEventType |
| `src/orbit/stream/cancellation.py` | 新 | ~40 | CancellationToken |
| `src/orbit/stream/sse.py` | 新 | ~120 | SSE 端点 + 取消端点 + run 端点 |
| `src/orbit/gateway/adapters/__init__.py` | 新 | 30 | ProviderAdapter ABC |
| `src/orbit/gateway/adapters/anthropic.py` | 新 | ~60 | Anthropic normalize |
| `src/orbit/gateway/adapters/openai.py` | 新 | ~40 | OpenAI normalize (mostly pass-through) |
| `src/orbit/gateway/routing.py` | 新 | ~80 | RoutingStrategy + 模型选择 |
| `src/orbit/agents/react_agent.py` | 改 | +100/-20 | execute_stream() + 旧 execute() wrapper |
| `src/orbit/agents/base.py` | 改 | +5 | 添加 execute_stream 抽象方法 |
| `src/orbit/agents/factory.py` | 改 | +10 | create 支持 cancel_token |
| `src/orbit/gateway/client.py` | 改 | +80/-10 | routing 集成 + adapter 管线 + _stream_completion_with_tools |
| `src/orbit/gateway/schemas.py` | 改 | +5 | LLMRequest.provider |
| `frontend/src/components/chat/ChatStream.vue` | 新 | ~120 | 流式文本展示 |
| `tests/unit/test_stream.py` | 新 | ~120 | 流式事件 + CancellationToken + SSE |
| `tests/unit/test_adapters.py` | 新 | ~100 | Anthropic + OpenAI adapter |
| `tests/unit/test_routing.py` | 新 | ~60 | RoutingStrategy 选择逻辑 |

**合计**: 11 新文件，5 修改文件，~1030 行新增，~30 行删除。

---

## 12. 实现步骤

| # | 步骤 | 文件 | 预估 |
|---|------|------|:--:|
| 1 | StreamEvent + CancellationToken 模型 | `stream/events.py` + `cancellation.py` | 30min |
| 2 | ProviderAdapter base + Anthropic/OpenAI | `gateway/adapters/` 3 文件 | 45min |
| 3 | RoutingStrategy | `gateway/routing.py` | 30min |
| 4 | gateway/client.py 集成 adapter + routing | `gateway/client.py` 改 | 45min |
| 5 | ReActAgent.execute_stream() | `agents/react_agent.py` 改 | 1h |
| 6 | SSE 端点 + cancel/run API | `stream/sse.py` | 45min |
| 7 | BaseAgent + Factory 适配 | `agents/base.py` + `factory.py` 改 | 20min |
| 8 | 驾驶舱 ChatStream 组件 | `frontend/.../ChatStream.vue` | 1h |
| 9 | 测试（unit × 3 文件） | `tests/unit/` 3 文件 | 1h |
| 10 | 全量回归 + CI | 全量 pytest | 30min |

**总预估**: ~7 小时（1 天），收敛到 3 天预算内。

---

## 13. 与后续组的接口约定

组 2（子Agent + Goal Judge）依赖本组以下产物：
- `ReActAgent.execute_stream(token)` — 子Agent 通过流式 generator 启动
- `StreamEvent` — 子Agent 事件透传到父 Agent
- `CancellationToken` — 父 Agent 取消子 Agent 的通道
- ProviderAdapter — Goal Judge 用 temperature=0 的独立 LLM 调用（不受 routing 影响）
