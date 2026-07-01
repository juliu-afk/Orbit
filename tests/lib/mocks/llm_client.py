"""Mock LLM 客户端——替代 gateway/client.py:LLMClient。

增强版：流式分块/工具调用模拟/失败序列/延迟/熵值控制。
基于 tests/e2e/mock_llm.py 迁移增强，旧位置保留 import 重定向。

使用示例:
    # 正常响应
    mock = MockLLMClient(fixed_response="print('ok')")
    # 前3次失败，第4次成功
    mock = MockLLMClient(fail_count=3, fixed_response="...")
    # 流式+工具调用
    mock = MockLLMClient(stream_chunks=["def ", "login", "(): ..."],
                         tool_calls=[{"name": "read_file", "args": {"path": "a.py"}}])
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage
from tests.lib.factories.llm import create_llm_response

logger = structlog.get_logger()


class LLMError(Exception):
    """模拟 LLM 调用失败（对应 litellm 抛出的异常）。"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"LLM error {status_code}: {message}")


class MockLLMClient:
    """Mock LLM 客户端——替代 gateway/client.py:LLMClient。

    实现 generate() + generate_stream_with_tools()，100% 兼容生产接口签名。
    支持链式配置: .with_failures(3).with_response(...).with_latency(0.5)
    """

    def __init__(
        self,
        fixed_response: LLMResponse | str | None = None,
        fail_count: int = 0,
        stream_chunks: list[str] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        latency_ms: int = 0,
        entropy: float = 0.0,
    ) -> None:
        self._fixed_response = self._normalize_response(fixed_response)
        self._fail_count = fail_count
        self._stream_chunks = stream_chunks or []
        self._tool_calls = tool_calls
        self._latency_ms = latency_ms
        self.entropy = entropy

        self.call_count: int = 0
        self.stream_call_count: int = 0
        self.calls: list[LLMRequest] = []
        self.stream_calls: list[LLMRequest] = []

    def with_response(self, response: LLMResponse | str) -> "MockLLMClient":
        self._fixed_response = self._normalize_response(response)
        return self

    def with_failures(self, count: int) -> "MockLLMClient":
        self._fail_count = count
        return self

    def with_stream(self, chunks: list[str]) -> "MockLLMClient":
        self._stream_chunks = chunks
        return self

    def with_tool_calls(self, calls: list[dict[str, Any]]) -> "MockLLMClient":
        self._tool_calls = calls
        return self

    def with_latency(self, ms: int) -> "MockLLMClient":
        self._latency_ms = ms
        return self

    async def generate(
        self,
        req: LLMRequest,
        task_id: str,
        agent_name: str = "",
        router_decision: Any = None,
        routing_strategy: Any = None,
    ) -> LLMResponse:
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        self.call_count += 1
        self.calls.append(req)

        if self.call_count <= self._fail_count:
            raise LLMError(500, f"Mock LLM internal error (call #{self.call_count})")

        if self._fixed_response is not None:
            return self._fixed_response

        tool_calls = self._tool_calls
        return LLMResponse(
            content="[mock] CODE_GENERATED_OK",
            model="mock-model",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30, cost_usd=0.0),
            tool_calls=tool_calls,
            stop_reason="tool_calls" if tool_calls else "end_turn",
            degraded=False,
        )

    async def generate_stream_with_tools(
        self, req: LLMRequest, task_id: str = "", agent_name: str = ""
    ):
        from orbit.stream.events import StreamEventType

        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        self.stream_call_count += 1
        self.stream_calls.append(req)

        if self.stream_call_count <= self._fail_count:
            yield (StreamEventType.ERROR, {
                "message": f"Mock LLM internal error (stream call #{self.stream_call_count})",
                "code": "MOCK_ERROR",
            })
            return

        if self._tool_calls:
            yield (StreamEventType.THINKING, {"content": "I need to read the file first."})
            for tc in self._tool_calls:
                yield (StreamEventType.TOOL_CALL, {
                    "tool": tc.get("name", "unknown"),
                    "args": tc.get("args", {}),
                })
            return

        chunks = self._stream_chunks or ([self._fixed_response.content] if self._fixed_response else ["[mock] OK"])
        for chunk in chunks:
            yield (StreamEventType.TEXT_DELTA, {"delta": chunk})

    def reset(self) -> None:
        self.call_count = 0
        self.stream_call_count = 0
        self.calls.clear()
        self.stream_calls.clear()

    @staticmethod
    def _normalize_response(response: LLMResponse | str | None) -> LLMResponse | None:
        if response is None:
            return None
        if isinstance(response, str):
            return create_llm_response(content=response)
        return response
