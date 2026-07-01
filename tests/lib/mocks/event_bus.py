"""Mock 事件总线——替代 events/bus.py:EventBus。

可配置队列满丢弃、订阅者行为。纯内存，追踪所有发布事件。
"""

from __future__ import annotations

import asyncio
from typing import Any


class MockEventBus:
    """Mock 事件总线——替代 events/bus.py:EventBus。100% 兼容 publish/subscribe 接口。"""

    def __init__(self, queue_full: bool = False, maxsize: int = 256) -> None:
        self.queue_full = queue_full
        self.maxsize = maxsize
        self.published: list[Any] = []
        self.dropped: list[Any] = []
        self.publish_count: int = 0
        self.dropped_count: int = 0
        self._subscribers: list[asyncio.Queue] = []

    def with_queue_full(self) -> "MockEventBus":
        self.queue_full = True
        return self

    def with_queue_ok(self) -> "MockEventBus":
        self.queue_full = False
        return self

    def publish(self, event: Any) -> None:
        self.publish_count += 1
        if self.queue_full:
            self.dropped.append(event)
            self.dropped_count += 1
            return
        self.published.append(event)
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> Any:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        self._subscribers.append(q)
        return await q.get()

    @property
    def event_count(self) -> int:
        return len(self.published)

    def get_events_by_type(self, event_type: str) -> list[Any]:
        """按事件类型过滤。兼容 dict 和对象类型事件。"""
        result = []
        for e in self.published:
            t = e.get("type") if isinstance(e, dict) else getattr(e, "type", None)
            if t == event_type:
                result.append(e)
        return result

    def reset(self) -> None:
        self.published.clear()
        self.dropped.clear()
        self.publish_count = 0
        self.dropped_count = 0
        self._subscribers.clear()
