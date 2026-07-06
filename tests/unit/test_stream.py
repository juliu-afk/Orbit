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
        data_line = [ln for ln in lines if ln.startswith("data: ")][0]
        data_json = data_line[6:]  # strip "data: "
        parsed = json.loads(data_json)
        assert parsed["type"] == "text_delta"

    def test_all_event_types_have_valid_values(self):
        from orbit.stream.events import StreamEventType

        valid_types = {
            "text_delta",
            "thinking",
            "tool_call",
            "tool_result",
            "turn_start",
            "finish_step",
            "error",
            "cancelled",
            "reflection",
            "metacog_alert",
            "hitl_request",
        }
        for t in StreamEventType:
            assert t.value in valid_types, f"Missing valid type: {t.value}"


# ── SSE 端点测试（覆盖 stream/sse.py）───────────────


class TestSSEEndpoints:
    """SSE 端点——agent_run / agent_stream / agent_cancel。"""

    @pytest.fixture
    def sse_client(self):
        """FastAPI TestClient——包含 SSE 路由。"""
        from unittest.mock import AsyncMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from orbit.stream.sse import router as sse_router

        app = FastAPI()
        app.include_router(sse_router)

        # 注入 mock llm/tools 到 app state
        app.state.llm = AsyncMock()
        app.state.tools = None

        return TestClient(app)

    def test_agent_run_returns_task_id(self, sse_client):
        """POST /api/v1/agent/dev/run → 返回 task_id。"""
        resp = sse_client.post(
            "/api/v1/agent/dev/run",
            json={"task": "hello world", "role": "developer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert len(data["data"]["task_id"]) == 12
        assert data["data"]["agent_id"] == "dev"

    def test_agent_cancel_unknown_task(self, sse_client):
        """POST cancel 不存在的 task → 404 code。"""
        resp = sse_client.post(
            "/api/v1/agent/dev/cancel",
            json={"task_id": "nonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 404

    def test_agent_cancel_existing_task(self, sse_client):
        """先 run 创建 token，再 cancel → 200。"""
        # 1. 创建 task
        run_resp = sse_client.post(
            "/api/v1/agent/dev/run",
            json={"task": "test", "role": "developer"},
        )
        task_id = run_resp.json()["data"]["task_id"]

        # 2. 取消
        cancel_resp = sse_client.post(
            "/api/v1/agent/dev/cancel",
            json={"task_id": task_id},
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["data"]["cancelled"] is True

    def test_agent_stream_endpoint_sets_headers(self, sse_client):
        """SSE 流式端点返回正确的 content-type 和 headers。"""
        from orbit.core.config import settings

        # 先创建 task
        run_resp = sse_client.post(
            "/api/v1/agent/dev/run",
            json={"task": "simple", "role": "developer"},
        )
        task_id = run_resp.json()["data"]["task_id"]

        # 连接 SSE 流（带 mock LLM——但请求可能因缺少真实 llm 而失败）
        # 测试 SSE headers 设置
        resp = sse_client.get(
            f"/api/v1/agent/dev/stream?task_id={task_id}&task=echo+hello&token={settings.ORBIT_AUTH_TOKEN}",
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert resp.headers.get("cache-control") == "no-cache"


# ── P2-5 (PR#130): verify_stream_token + _is_public_path 覆盖测试 ──


class TestAuthCoverage:
    """verify_stream_token 鉴权 + _is_public_path 公开路径判定。"""

    def test_verify_stream_token_correct(self):
        """正确 token → 返回 token 字符串（P1-1: Header 优先）。"""
        from orbit.api.dependencies import verify_stream_token
        from orbit.core.config import settings

        result = verify_stream_token(token_header=settings.ORBIT_AUTH_TOKEN)
        assert result == settings.ORBIT_AUTH_TOKEN

    def test_verify_stream_token_wrong(self):
        """错误 token → HTTPException 403。"""
        from fastapi import HTTPException

        from orbit.api.dependencies import verify_stream_token

        with pytest.raises(HTTPException) as exc_info:
            verify_stream_token(token_header="wrong-token")
        assert exc_info.value.status_code == 403

    def test_verify_stream_token_empty(self):
        """空 token → HTTPException 403。"""
        from fastapi import HTTPException

        from orbit.api.dependencies import verify_stream_token

        with pytest.raises(HTTPException) as exc_info:
            # P1-1: 无 Header 也无 Query → 403
            verify_stream_token(token_header=None, token_query=None)
        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/health", True),
            ("/metrics", True),
            ("/docs", True),
            ("/redoc", True),
            ("/openapi.json", True),
            ("/assets/app.js", True),
            ("/assets", True),  # P1-7: 无尾部斜杠也应放行
            ("/assets/", True),
            ("/api/v1/tasks", False),
            ("/api/v1/loop", False),
            ("/ws", False),
        ],
    )
    def test_is_public_path(self, path, expected):
        """公开路径判定——健康/文档/静态资源放行，API 端点拒绝。"""
        from orbit.api.dependencies import _is_public_path

        assert _is_public_path(path) == expected


# ── 流式 Gateway Client 测试 ────────────────────────


class TestGatewayStreaming:
    """LLMClient.generate_stream_with_tools——流式 LLM 调用。"""

    @pytest.mark.asyncio
    async def test_generate_stream_with_tools_text_only(self):
        """流式调用——纯文本输出，无工具调用。"""
        from unittest.mock import patch

        from orbit.gateway.client import LLMClient
        from orbit.gateway.schemas import LLMRequest
        from orbit.stream.events import StreamEventType

        client = LLMClient()

        # Mock _stream_completion_with_tools——避免依赖 litellm
        async def mock_stream(model, req):
            yield (StreamEventType.TEXT_DELTA, {"delta": "hello"})

        with patch.object(client, "_stream_completion_with_tools", new=mock_stream):
            events = []
            async for event_type, data in client.generate_stream_with_tools(
                LLMRequest(prompt="test"), task_id="t1"
            ):
                events.append((event_type, data))

        text_events = [d for t, d in events if t == StreamEventType.TEXT_DELTA]
        assert len(text_events) > 0
        assert text_events[0]["delta"] == "hello"

    @pytest.mark.asyncio
    async def test_generate_stream_with_tools_error(self):
        """流式调用——primary 失败后 fallback 成功。"""
        from unittest.mock import patch

        from orbit.gateway.client import LLMClient
        from orbit.gateway.schemas import LLMRequest
        from orbit.stream.events import StreamEventType

        client = LLMClient()

        # 第一次调用失败，第二次成功
        call_count = [0]

        async def mock_stream_primary(model, req):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("primary failed")
            yield (StreamEventType.TEXT_DELTA, {"delta": "fallback ok"})

        with patch.object(client, "_stream_completion_with_tools", new=mock_stream_primary):
            events = []
            async for event_type, data in client.generate_stream_with_tools(
                LLMRequest(prompt="test"), task_id="t2"
            ):
                events.append((event_type, data))

        text_events = [d for t, d in events if t == StreamEventType.TEXT_DELTA]
        assert len(text_events) > 0
        assert text_events[0]["delta"] == "fallback ok"
