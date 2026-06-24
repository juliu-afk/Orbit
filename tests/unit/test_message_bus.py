"""Step 5.4 PR #1——Agent 消息总线单元测试。"""

import asyncio

import pytest

from orbit.communication.message_bus import (
    AgentMessageBus,
    AgentUnavailableError,
)
from orbit.communication.protocol import (
    ErrorCode,
    Notification,
    Request,
    Response,
    ResponseStatus,
)


def _echo_handler(req: Request) -> Response:
    """回显 handler——返回 params 中的内容。"""
    return Response(
        id=f"resp-{req.id}",
        correlation_id=req.id,
        source_agent=req.target_agent,
        target_agent=req.source_agent,
        status=ResponseStatus.SUCCESS,
        result=req.params,
    )


class TestAgentMessageBus:
    """消息总线——注册/请求/幂等/超时/熔断。"""

    @pytest.mark.asyncio
    async def test_register_and_is_registered(self) -> None:
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        assert bus.is_registered("QA") is True
        assert bus.is_registered("Nope") is False

    @pytest.mark.asyncio
    async def test_unregister(self) -> None:
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        bus.unregister("QA")
        assert bus.is_registered("QA") is False

    @pytest.mark.asyncio
    async def test_request_response_success(self) -> None:
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        req = Request(
            source_agent="Dev",
            target_agent="QA",
            method="verify",
            params={"code": "ok"},
        )
        resp = await bus.request(req)
        assert resp.status == ResponseStatus.SUCCESS
        assert resp.result == {"code": "ok"}

    @pytest.mark.asyncio
    async def test_request_target_unavailable(self) -> None:
        bus = AgentMessageBus()
        req = Request(source_agent="Dev", target_agent="Ghost")
        with pytest.raises(AgentUnavailableError):
            await bus.request(req)

    @pytest.mark.asyncio
    async def test_idempotent_deduplication(self) -> None:
        """相同 request_id 第二次返回缓存响应，不重新执行。"""
        bus = AgentMessageBus()
        call_count = 0

        def counting_handler(r: Request) -> Response:
            nonlocal call_count
            call_count += 1
            return Response(
                id=f"resp-{r.id}",
                correlation_id=r.id,
                source_agent="QA",
                target_agent="Dev",
                status=ResponseStatus.SUCCESS,
                result={"called": call_count},
            )

        bus.register("QA", counting_handler)
        req = Request(id="req-1", source_agent="Dev", target_agent="QA", method="test")
        resp1 = await bus.request(req)
        assert resp1.result == {"called": 1}
        # 第二次相同 ID——应返回缓存
        resp2 = await bus.request(req)
        assert resp2.result == {"called": 1}  # 未重新执行

    @pytest.mark.asyncio
    async def test_circuit_open_returns_response(self) -> None:
        """下游熔断时返回 status=circuit_open (不抛异常, 调用方可降级)。"""
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        bus.set_circuit_open("QA", True)
        req = Request(source_agent="Dev", target_agent="QA", method="test")
        resp = await bus.request(req)
        assert resp.status == ResponseStatus.CIRCUIT_OPEN
        assert resp.error_code == ErrorCode.AGENT_CIRCUIT_OPEN

    @pytest.mark.asyncio
    async def test_notification_fire_and_forget(self) -> None:
        """通知发送不等待响应。"""
        bus = AgentMessageBus()
        received: list[str] = []

        def notif_handler(r: Request) -> Response:
            received.append(r.method)
            return Response(
                id=f"resp-{r.id}",
                correlation_id=r.id,
                source_agent="QA",
                target_agent="Dev",
                status=ResponseStatus.SUCCESS,
            )

        bus.register("QA", notif_handler)
        notif = Notification(
            source_agent="Dev",
            event="task_completed",
            payload={"task_id": "t1"},
        )
        bus.notify(notif)
        await asyncio.sleep(0.05)  # 等待异步投递完成
        # 通知投递给了 QA
        assert len(received) >= 1

    @pytest.mark.asyncio
    async def test_streaming(self) -> None:
        """流式请求返回 StreamChunk 序列。"""
        bus = AgentMessageBus()
        bus.register("Sandbox", _echo_handler)
        req = Request(
            source_agent="Dev",
            target_agent="Sandbox",
            method="execute",
            params={"script": "print(1)"},
        )
        chunks = []
        async for chunk in bus.stream(req):
            chunks.append(chunk)
        assert len(chunks) >= 1
        assert chunks[-1].is_last is True

    @pytest.mark.asyncio
    async def test_stream_circuit_open(self) -> None:
        """流式通道也传播熔断。"""
        bus = AgentMessageBus()
        bus.register("Sandbox", _echo_handler)
        bus.set_circuit_open("Sandbox", True)
        req = Request(source_agent="Dev", target_agent="Sandbox", method="test")
        chunks = []
        async for chunk in bus.stream(req):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "AGENT_003" in chunks[0].error

    @pytest.mark.asyncio
    async def test_audit_records(self) -> None:
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        req = Request(source_agent="Dev", target_agent="QA", method="test")
        await bus.request(req)
        audit = bus.get_audit()
        assert len(audit) >= 1
        assert audit[-1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_queue_status(self) -> None:
        bus = AgentMessageBus()
        bus.register("QA", _echo_handler)
        bus.register("Dev", _echo_handler)
        status = bus.get_queue_status()
        assert status["registered_agents"] == 2
        assert status["pending_requests"] == 0
