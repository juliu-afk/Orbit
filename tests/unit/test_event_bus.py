"""EventBus 单元测试。

事件总线核心行为：发布→订阅、队列满丢弃、事件序列化。
"""

import asyncio

import pytest

from orbit.events.bus import EventBus
from orbit.events.schemas import AlertPayload, DashboardEvent, TaskUpdatePayload


class TestEventBus:
    """EventBus 发布-订阅流转。"""

    def test_publish_and_subscribe(self):
        """发布事件后订阅者能收到相同事件。"""
        bus = EventBus(maxsize=8)

        event = DashboardEvent(
            type="task:update",
            task_id="test-task-1",
            payload=TaskUpdatePayload(
                task_id="test-task-1",
                state="CODING",
                progress=0.5,
                dag=[],
                timestamp="2026-01-01T00:00:00",
            ).model_dump(),
        )

        bus.publish(event)

        async def consume():
            received = await bus.subscribe()
            assert received.type == "task:update"
            assert received.task_id == "test-task-1"
            assert received.payload["state"] == "CODING"

        asyncio.run(consume())

    def test_queue_full_drops_oldest(self):
        """队列满时 put_nowait 抛 QueueFull，publish 不阻塞且不抛异常。"""
        bus = EventBus(maxsize=2)

        for i in range(4):
            event = DashboardEvent(
                type="task:update",
                task_id=f"task-{i}",
                payload={"i": i},
            )
            # publish 不应抛异常——队列满时丢弃
            bus.publish(event)

        # 队列中只有前 2 个（后 2 个被丢弃）
        async def consume_all():
            events = []
            while not bus._queue.empty():
                events.append(await bus.subscribe())
            return events

        events = asyncio.run(consume_all())
        assert len(events) == 2

    def test_event_serialization(self):
        """DashboardEvent 可序列化为 dict 供 WebSocket send_json 使用。"""
        event = DashboardEvent(
            type="alert:new",
            task_id="t1",
            payload=AlertPayload(
                task_id="t1",
                level="l3_entropy",
                severity="warning",
                message="熵超阈值",
                timestamp="2026-01-01T00:00:00",
            ).model_dump(),
        )

        data = event.model_dump()
        assert data["type"] == "alert:new"
        assert data["payload"]["level"] == "l3_entropy"
        # 确保 timestamp 可 JSON 序列化
        import json
        json.dumps(data, default=str)  # 不应抛异常

    def test_subscriber_blocks_on_empty(self):
        """空队列时 subscribe 阻塞，publish 后唤醒。"""
        bus = EventBus(maxsize=4)

        received = []

        async def delayed_publish():
            await asyncio.sleep(0.01)
            bus.publish(DashboardEvent(
                type="task:update",
                task_id="delayed",
                payload={},
            ))

        async def consume():
            event = await bus.subscribe()
            received.append(event.task_id)

        async def runner():
            await asyncio.gather(consume(), delayed_publish())

        asyncio.run(runner())
        assert received == ["delayed"]
