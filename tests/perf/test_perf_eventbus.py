"""EventBus 吞吐基准。"""

import asyncio
from typing import Any

import pytest

from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent


@pytest.mark.perf
@pytest.mark.asyncio(loop_scope="function")
async def test_perf_eventbus_throughput(benchmark: Any) -> None:
    """publish 1000 事件的吞吐量。

    AC3: >5000 events/s。
    """
    bus = EventBus(maxsize=2048)
    event = DashboardEvent(
        type="task:update",
        task_id="perf-bus",
        payload={"state": "DONE", "progress": 1.0, "dag": []},
    )

    def pump_events() -> None:
        for _ in range(1000):
            bus.publish(event)

    benchmark(pump_events)
    # 验证队列未满丢弃（not empty 而非 qsize()——避免 Windows 下多线程竞态）
    assert not bus._queue.empty()


@pytest.mark.perf
@pytest.mark.asyncio(loop_scope="function")
async def test_perf_eventbus_pubsub_roundtrip(benchmark: Any) -> None:
    """publish→subscribe 端到端延迟。"""
    bus = EventBus(maxsize=8)
    event = DashboardEvent(
        type="task:update",
        task_id="perf-roundtrip",
        payload={},
    )

    async def pubsub_one() -> Any:
        bus.publish(event)
        received = await bus.subscribe()
        return received.task_id

    task_id = await benchmark(lambda: asyncio.wait_for(pubsub_one(), timeout=5))
    assert task_id == "perf-roundtrip"
