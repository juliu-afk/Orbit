"""Agent 通信协议数据模型测试。

测试所有 4 种消息类型：Request/Response/Notification/StreamChunk。
纯 dataclass 序列化，无外部依赖。
"""

from __future__ import annotations

from orbit.communication.protocol import (
    ErrorCode,
    Message,
    MessageType,
    Notification,
    Request,
    Response,
    ResponseStatus,
    StreamChunk,
)


class TestMessageType:
    def test_enum_values(self) -> None:
        assert MessageType.REQUEST.value == "request"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.NOTIFICATION.value == "notification"
        assert MessageType.STREAM_CHUNK.value == "stream_chunk"


class TestResponseStatus:
    def test_enum_values(self) -> None:
        assert ResponseStatus.SUCCESS.value == "success"
        assert ResponseStatus.ERROR.value == "error"
        assert ResponseStatus.TIMEOUT.value == "timeout"
        assert ResponseStatus.CIRCUIT_OPEN.value == "circuit_open"


class TestErrorCode:
    def test_enum_values(self) -> None:
        assert ErrorCode.AGENT_UNAVAILABLE.value == "AGENT_001"
        assert ErrorCode.AGENT_TIMEOUT.value == "AGENT_002"
        assert ErrorCode.AGENT_CIRCUIT_OPEN.value == "AGENT_003"
        assert ErrorCode.AGENT_RATE_LIMITED.value == "AGENT_006"


class TestMessage:
    """消息基类——所有 Agent 间消息的公共字段。"""

    def test_defaults(self) -> None:
        msg = Message()
        assert msg.id is not None  # UUID 自动生成
        assert msg.correlation_id == ""
        assert msg.source_agent == ""
        assert msg.target_agent == ""
        assert msg.timestamp == 0.0

    def test_full_construction(self) -> None:
        msg = Message(
            id="msg-1",
            correlation_id="corr-1",
            source_agent="agent-a",
            target_agent="agent-b",
            timestamp=100.0,
        )
        assert msg.id == "msg-1"
        assert msg.correlation_id == "corr-1"
        assert msg.source_agent == "agent-a"
        assert msg.target_agent == "agent-b"
        assert msg.timestamp == 100.0

    def test_to_dict(self) -> None:
        msg = Message(
            id="test-id",
            correlation_id="corr-1",
            source_agent="src",
            target_agent="dst",
            timestamp=50.0,
        )
        d = msg.to_dict()
        assert d["id"] == "test-id"
        assert d["correlation_id"] == "corr-1"
        assert d["source_agent"] == "src"
        assert d["target_agent"] == "dst"
        assert d["timestamp"] == 50.0


class TestRequest:
    """Request-Response 模式——同步等待响应。"""

    def test_defaults(self) -> None:
        req = Request()
        assert req.type == MessageType.REQUEST
        assert req.method == ""
        assert req.params == {}
        assert req.timeout_seconds == 30
        assert req.retry_count == 0

    def test_full_construction(self) -> None:
        req = Request(
            method="verify",
            params={"code": "def f(): pass"},
            timeout_seconds=60,
            retry_count=2,
            source_agent="orchestrator",
            target_agent="reviewer",
        )
        assert req.method == "verify"
        assert req.params == {"code": "def f(): pass"}
        assert req.timeout_seconds == 60
        assert req.retry_count == 2
        assert req.source_agent == "orchestrator"
        assert req.target_agent == "reviewer"

    def test_to_dict(self) -> None:
        req = Request(
            id="req-1",
            method="execute",
            params={"task": "test"},
            timeout_seconds=30,
            retry_count=1,
        )
        d = req.to_dict()
        assert d["type"] == "request"
        assert d["method"] == "execute"
        assert d["params"] == {"task": "test"}
        assert d["timeout_seconds"] == 30
        assert d["retry_count"] == 1


class TestResponse:
    """Request 的响应——同步返回。"""

    def test_defaults(self) -> None:
        resp = Response()
        assert resp.type == MessageType.RESPONSE
        assert resp.status == ResponseStatus.SUCCESS
        assert resp.result is None
        assert resp.error_code == ""
        assert resp.error_message == ""
        assert resp.duration_ms == 0.0

    def test_success_response(self) -> None:
        resp = Response(
            correlation_id="req-1",
            status=ResponseStatus.SUCCESS,
            result={"output": "done"},
            duration_ms=123.4,
        )
        assert resp.status == "success"
        assert resp.result == {"output": "done"}
        assert resp.duration_ms == 123.4

    def test_error_response(self) -> None:
        resp = Response(
            status=ResponseStatus.ERROR,
            error_code=ErrorCode.AGENT_TIMEOUT,
            error_message="请求超时",
            duration_ms=5000.0,
        )
        assert resp.status == "error"
        assert resp.error_code == "AGENT_002"
        assert resp.error_message == "请求超时"

    def test_circuit_open_response(self) -> None:
        resp = Response(
            status=ResponseStatus.CIRCUIT_OPEN,
            error_code=ErrorCode.AGENT_CIRCUIT_OPEN,
            error_message="熔断开启",
        )
        assert resp.status == "circuit_open"
        assert resp.error_code == "AGENT_003"

    def test_timeout_response(self) -> None:
        resp = Response(status=ResponseStatus.TIMEOUT)
        assert resp.status == "timeout"

    def test_to_dict(self) -> None:
        resp = Response(
            id="resp-1",
            correlation_id="req-1",
            status=ResponseStatus.SUCCESS,
            result={"output": "done"},
            duration_ms=123.4,
        )
        d = resp.to_dict()
        assert d["result"] == {"output": "done"}
        assert d["duration_ms"] == 123.4
        assert d["correlation_id"] == "req-1"


class TestNotification:
    """Fire-and-Forget 模式——发送后不等待响应。"""

    def test_defaults(self) -> None:
        n = Notification()
        assert n.type == MessageType.NOTIFICATION
        assert n.event == ""
        assert n.payload == {}

    def test_full_construction(self) -> None:
        n = Notification(
            event="task_completed",
            payload={"task_id": "t-1", "status": "done"},
            source_agent="developer",
        )
        assert n.event == "task_completed"
        assert n.payload["task_id"] == "t-1"
        assert n.source_agent == "developer"

    def test_to_dict(self) -> None:
        n = Notification(
            id="notif-1",
            event="agent_error",
            payload={"error": "timeout"},
        )
        d = n.to_dict()
        assert d["event"] == "agent_error"
        assert d["payload"] == {"error": "timeout"}


class TestStreamChunk:
    """流式数据块——长耗时操作分块推送。"""

    def test_defaults(self) -> None:
        s = StreamChunk()
        assert s.type == MessageType.STREAM_CHUNK
        assert s.sequence == 0
        assert s.data == ""
        assert s.is_last is False
        assert s.error == ""

    def test_first_chunk(self) -> None:
        s = StreamChunk(sequence=0, data="hello", is_last=False)
        assert s.sequence == 0
        assert s.data == "hello"
        assert s.is_last is False

    def test_last_chunk(self) -> None:
        s = StreamChunk(sequence=2, data="done", is_last=True)
        assert s.sequence == 2
        assert s.is_last is True

    def test_chunk_with_error(self) -> None:
        s = StreamChunk(sequence=1, data="partial", error="connection lost")
        assert s.error == "connection lost"

    def test_to_dict(self) -> None:
        s = StreamChunk(
            id="chunk-1",
            sequence=0,
            data="hello world",
            is_last=False,
            source_agent="developer",
        )
        d = s.to_dict()
        assert d["sequence"] == 0
        assert d["data"] == "hello world"
        assert d["is_last"] is False
        assert d["source_agent"] == "developer"
