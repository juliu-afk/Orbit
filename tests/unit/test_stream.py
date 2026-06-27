"""流式模块单元测试——StreamEvent + CancellationToken + SSE.

Phase 3 组 1 (AC19): 覆盖流式事件模型、取消令牌、SSE 格式。
"""

from __future__ import annotations

import json

import pytest


class TestStreamEvent:
    """StreamEvent 模型测试。"""

    def test_text_delta_event(self):
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            agent_id="developer",
            task_id="test123",
            turn=1,
            data={"delta": "hello"},
        )
        assert event.type == StreamEventType.TEXT_DELTA
        assert event.agent_id == "developer"
        assert event.turn == 1
        assert event.data["delta"] == "hello"

    def test_tool_call_event(self):
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.TOOL_CALL,
            agent_id="developer",
            task_id="test123",
            turn=2,
            data={"tool": "read_file", "args": {"path": "test.py"}},
        )
        assert event.type == StreamEventType.TOOL_CALL
        assert event.data["tool"] == "read_file"

    def test_finish_step_event(self):
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.FINISH_STEP,
            task_id="test123",
            data={"output": "done", "turns": 5, "tool_calls": 12},
        )
        assert event.type == StreamEventType.FINISH_STEP
        assert event.data["turns"] == 5

    def test_error_event(self):
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.ERROR,
            task_id="test123",
            data={"message": "timeout", "code": "MAX_TURNS"},
        )
        assert event.type == StreamEventType.ERROR
        assert event.data["code"] == "MAX_TURNS"

    def test_json_serializable(self):
        """SSE 端点依赖 model_dump_json() 序列化事件。"""
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            task_id="test123",
            turn=3,
            data={"delta": "some text"},
        )
        dumped = event.model_dump_json()
        parsed = json.loads(dumped)
        assert parsed["type"] == "text_delta"
        assert parsed["turn"] == 3


class TestCancellationToken:
    """CancellationToken 测试。"""

    def test_initial_state_not_cancelled(self):
        from orbit.stream.cancellation import CancellationToken

        token = CancellationToken()
        assert token.is_cancelled is False

    def test_cancel_sets_flag(self):
        from orbit.stream.cancellation import CancellationToken

        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled is True

    def test_cancel_idempotent(self):
        """多次 cancel 安全。"""
        from orbit.stream.cancellation import CancellationToken

        token = CancellationToken()
        token.cancel()
        token.cancel()
        token.cancel()
        assert token.is_cancelled is True

    @pytest.mark.asyncio
    async def test_wait_if_cancelled_immediate(self):
        from orbit.stream.cancellation import CancellationToken

        token = CancellationToken()
        assert await token.wait_if_cancelled(timeout=0.0) is False
        token.cancel()
        assert await token.wait_if_cancelled(timeout=0.0) is True

    @pytest.mark.asyncio
    async def test_wait_if_cancelled_with_timeout(self):
        from orbit.stream.cancellation import CancellationToken

        token = CancellationToken()
        # 未取消 + timeout → 返回 False
        result = await token.wait_if_cancelled(timeout=0.01)
        assert result is False


class TestSSEEventFormat:
    """SSE 格式测试——确保前端兼容。"""

    def test_sse_format_text_delta(self):
        from orbit.stream.events import StreamEvent, StreamEventType

        event = StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            agent_id="dev",
            task_id="t1",
            data={"delta": "hello"},
        )
        event_type = event.type.value
        event_json = event.model_dump_json()
        sse_frame = f"event: {event_type}\ndata: {event_json}\n\n"
        assert sse_frame.startswith("event: text_delta\n")
        assert "data: " in sse_frame
        assert sse_frame.endswith("\n\n")
        # 验证 JSON 可解析
        lines = sse_frame.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = data_line[6:]  # strip "data: "
        parsed = json.loads(data_json)
        assert parsed["type"] == "text_delta"

    def test_all_event_types_have_valid_values(self):
        from orbit.stream.events import StreamEventType

        valid_types = {
            "text_delta", "thinking", "tool_call", "tool_result",
            "turn_start", "finish_step", "error", "cancelled",
        }
        for t in StreamEventType:
            assert t.value in valid_types, f"Missing valid type: {t.value}"
