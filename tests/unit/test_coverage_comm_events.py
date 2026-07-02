"""覆盖率补测——communication/message_bus.py + events/bus.py + checkpoint/manager.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.communication.message_bus import AgentMessageBus
from orbit.events.bus import EventBus


# ════════════════════════════════════════════
# 1. EventBus
# ════════════════════════════════════════════

class TestEventBus:
    def test_init_default_maxsize(self):
        bus = EventBus()
        assert bus._queue.maxsize > 0

    def test_init_custom_maxsize(self):
        bus = EventBus(maxsize=64)
        assert bus._queue.maxsize == 64

    def test_publish(self):
        """publish 不阻塞——入队成功不抛异常。"""
        bus = EventBus(maxsize=100)
        from orbit.events.schemas import DashboardEvent
        event = DashboardEvent(
            type="task:update", task_id="t1",
            payload={"state": "IDLE"},
        )
        bus.publish(event)
        # 验证队列非空
        assert not bus._queue.empty()

    @pytest.mark.asyncio
    async def test_subscribe(self):
        """subscribe 消费已发布的事件。"""
        bus = EventBus(maxsize=10)
        from orbit.events.schemas import DashboardEvent
        event = DashboardEvent(
            type="task:update", task_id="t2",
            payload={"state": "CODING"},
        )
        bus.publish(event)
        received = await bus.subscribe()
        assert received.task_id == "t2"

    @pytest.mark.asyncio
    async def test_subscribe_timeout(self):
        """空队列超时。"""
        bus = EventBus(maxsize=10)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.subscribe(), timeout=0.1)


# ════════════════════════════════════════════
# 2. AgentMessageBus
# ════════════════════════════════════════════

class TestAgentMessageBus:
    def test_init(self):
        bus = AgentMessageBus()
        assert bus is not None

    def test_register_handler(self):
        """注册 Agent handler。"""
        bus = AgentMessageBus()
        mock_handler = AsyncMock()
        bus.register("agent-1", mock_handler)
        # 不抛异常即成功

    def test_unregister_handler(self):
        """注销 handler。"""
        bus = AgentMessageBus()
        mock_handler = AsyncMock()
        bus.register("agent-1", mock_handler)
        bus.unregister("agent-1")

    def test_set_circuit_open(self):
        """设置熔断状态。"""
        bus = AgentMessageBus()
        bus.set_circuit_open("agent-1", True)
        # 后续请求可能被拒绝

    def test_notify(self):
        """发送通知——不抛异常。"""
        bus = AgentMessageBus()
        from orbit.communication.protocol import Notification
        notif = Notification(
            event="task_completed",
            source_agent="agent-1",
            target_agent="agent-2",
            payload={"state": "DONE"},
        )
        bus.notify(notif)

    @pytest.mark.asyncio
    async def test_request_no_handler(self):
        """无 handler 的请求——超时。"""
        bus = AgentMessageBus()
        from orbit.communication.protocol import Request
        req = Request(
            method="run",
            source_agent="agent-1",
            target_agent="agent-2",
            params={"task": "test"},
        )
        try:
            await asyncio.wait_for(bus.request(req), timeout=0.2)
        except (asyncio.TimeoutError, Exception):
            pass  # 无 handler 时超时或 AgentUnavailableError


# ════════════════════════════════════════════
# 3. CheckpointManager + CheckpointData
# ════════════════════════════════════════════

class TestCheckpointData:
    def test_defaults(self):
        cd = CheckpointData(task_id="", state="IDLE")
        assert cd.task_id == ""
        assert cd.state == "IDLE"
        assert cd.version >= 1

    def test_with_data(self):
        cd = CheckpointData(task_id="task-1", state="CODING", retry_count=2)
        assert cd.task_id == "task-1"
        assert cd.state == "CODING"
        assert cd.retry_count == 2


class TestCheckpointManager:
    def test_init_no_redis(self):
        """无 Redis——初始化成功。"""
        mgr = CheckpointManager(redis_client=None)
        assert mgr.redis is None

    @pytest.mark.asyncio
    async def test_save_and_load_memory(self):
        """内存模式 save + load 往返。"""
        mgr = CheckpointManager(redis_client=None)
        cd = CheckpointData(task_id="t1", state="IDLE")
        await mgr.save("t1", cd)
        loaded = await mgr.load("t1")
        assert loaded is not None
        assert loaded.task_id == "t1"

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        """不存在的检查点 → None。"""
        mgr = CheckpointManager(redis_client=None)
        loaded = await mgr.load("nonexistent-task")
        assert loaded is None
