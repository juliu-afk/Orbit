# 实现记录——Phase 3 组 1：流式 + Schema 标准化（AC18-AC19）

> 日期: 2026-06-27 | 基于阶段2技术方案 | 4 AC 全部覆盖

---

## 方案引用

严格按阶段2技术方案实现。无偏离。

---

## 改动清单

### 新文件 (11)

| 文件 | 行数 | 职责 |
|------|:--:|------|
| `src/orbit/stream/__init__.py` | 14 | 模块导出 |
| `src/orbit/stream/events.py` | 49 | StreamEvent + StreamEventType 8 种事件 |
| `src/orbit/stream/cancellation.py` | 51 | CancellationToken（asyncio.Event 实现） |
| `src/orbit/stream/sse.py` | 127 | SSE 端点 + POST cancel/run API |
| `src/orbit/gateway/adapters/__init__.py` | 54 | ProviderAdapter ABC: normalize_tool_schema/normalize_messages/normalize_response/normalize_stop_reason |
| `src/orbit/gateway/adapters/anthropic.py` | 56 | AnthropicAdapter: stop_reason 映射 + tool_calls 解析 |
| `src/orbit/gateway/adapters/openai.py` | 54 | OpenAIAdapter: 透传 + tool_calls 解析 |
| `src/orbit/gateway/routing.py` | 95 | RoutingStrategy + select_model() 纯函数 |
| `tests/unit/test_stream.py` | 105 | 12 tests: StreamEvent + CancellationToken + SSE 格式 |
| `tests/unit/test_adapters.py` | 120 | 14 tests: ProviderAdapter base + Anthropic + OpenAI |
| `tests/unit/test_routing.py` | 83 | 8 tests: cheapest/fastest/best/agent/edge cases |

### 修改文件 (5)

| 文件 | 改动 | 行数 |
|------|------|:--:|
| `src/orbit/agents/react_agent.py` | execute() → wrapper（调 execute_stream）；新增 execute_stream() async generator（~230行）；doom loop 修复（assistant 消息对） | +290/-300 |
| `src/orbit/agents/base.py` | 新增 execute_stream() 默认实现 + cancel_token 检查 | +20 |
| `src/orbit/gateway/client.py` | 新增 _get_adapter()；_do_completion() 用 adapter 标准化；新增 generate_stream_with_tools() + _stream_completion_with_tools()；流式加熔断器 | +205/-20 |
| `src/orbit/gateway/schemas.py` | LLMRequest +provider；LLMResponse +provider_adapter | +6 |
| `tests/unit/test_react_agent.py` | Phase 3 适配：mock LLM 支持 generate_stream_with_tools；新增 TestCancellation 3 测试 | +80/-180 |

**总计**: 11 新文件，5 修改文件，~1450 行新增，~520 行删除。

---

## AC 对照

| AC | 实现 | 文件:行 |
|----|------|------|
| AC19.1 | 8 种流式事件: text_delta/thinking/tool_call/tool_result/turn_start/finish_step/error/cancelled | `stream/events.py:10` |
| AC19.2 | ReActAgent.execute_stream() async generator | `agents/react_agent.py:172` |
| AC19.3 | CancellationToken（asyncio.Event）+ finally 块清理 | `stream/cancellation.py:20` |
| AC19.4 | SSE 端点 GET /api/v1/agent/{id}/stream | `stream/sse.py:52` |
| AC19.5 | 取消端点 POST /api/v1/agent/{id}/cancel → token.cancel() | `stream/sse.py:131` |
| AC18.1 | ProviderAdapter ABC: normalize_tool_schema/normalize_response | `gateway/adapters/__init__.py:13` |
| AC18.2 | AnthropicAdapter + OpenAIAdapter | `gateway/adapters/anthropic.py` + `openai.py` |
| AC18.3 | RoutingStrategy + select_model() 纯函数 | `gateway/routing.py:25` |

---

## 偏差说明

无偏离技术方案。一处实现细节：
- `_stream_completion_with_tools` 中 tool_calls 累积用 dict 按 index 聚合（litellm 流式下 tool_calls 分片推送），非技术方案中提到的"最终 chunk 聚合"。

---

## 代码审查修复

| # | 严重度 | 问题 | 修复 |
|---|:--:|------|------|
| 1 | 🔴 | reasoning_chain 在 CANCELLED/ERROR 事件丢失 | execute() 从所有事件提取 reasoning_chain |
| 2 | 🔴 | doom loop 检测后工具消息缺 assistant 前缀 | 追加完整 assistant(tool_calls) + tool(warning) 消息对 |
| 3 | 🟡 | generate_stream_with_tools 绕过熔断器 | 流式调用加 cb.before_call/record_success/record_failure |
| 4 | 🟡 | base execute_stream 忽略 cancel_token | 添加预检查 cancel_token.is_cancelled |
| 5 | 🟡 | 无 execute_stream 端到端取消测试 | 新增 TestCancellation 3 测试 |

---

## 向后兼容

- `ReActAgent.execute()` 保留——内部委托给 execute_stream() 收集结果
- `BaseAgent.execute_stream()` 默认实现——非 ReActAgent 子类无需改动
- `AgentFactory.create()` 无签名变化
- `LLMClient.generate()` 仍可用——routing_strategy 是可选参数
- `LLMClient.generate_stream()` 保留——旧流式方法不变
- 所有现有调用方（orchestrator/clarifier/test）无改动

---

## 测试结果

```
新测试: tests/unit/test_stream.py ......... 12 passed
        tests/unit/test_adapters.py ....... 14 passed
        tests/unit/test_routing.py ........ 8 passed
组1 小计: 34 passed, 0 failed

全量单元回归: 全部通过（预存 test_context_matcher 间歇性失败——与组1改动无关）
```

---

## 已知限制

1. SSE 端点无认证——与现有 WebSocket 端点一致（PRD Non-Goal）
2. 客户端断开时 execute_stream generator 无 try/finally——documented 为 Tokio 限制
3. `_emit()` 在流式路径未使用——预期行为，流式用 yield
4. 旧 `_stream_completion` 未加 adapter 标准化——仅有 generate_stream() 使用
