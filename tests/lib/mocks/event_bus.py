"""Mock 事件总线——替代 events/bus.py:EventBus。

可配置队列满丢弃、订阅者行为。
用于测试中替代 asyncio.Queue 事件总线。

使用示例:
    # 正常
    bus = MockEventBus()
    # 队列满→丢弃
    bus = MockEventBus(queue_full=True)
"""

from __future__ import annotations

import asyncio
from typing import Any


class MockEventBus:
    """Mock 事件总线——替代 events/bus.py:EventBus。

    100% 兼容 publish()/subscribe() 接口签名。纯内存，跟踪所有发布事件。
    """

    def __init__(
        self,
        queue_full: bool = False,
        maxsize: int = 256,
    ) -> None:
        """初始化 Mock 事件总线。

        Args:
            queue_full: True→publish 静默丢弃事件（模拟 QueueFull）
            maxsize: 队列最大容量（仅用于追踪，不影响功能）
        """
        self.queue_full = queue_full
        self.maxsize = maxsize

        # 发布追踪
        self.published: list[Any] = []
        self.dropped: list[Any] = []  # queue_full 时被丢弃的事件
        self.publish_count: int = 0
        self.dropped_count: int = 0

        # 订阅者模拟
        self._subscribers: list[asyncio.Queue] = []

    # ── 链式配置方法 ──────────────────────────────────────

    def with_queue_full(self) -> "MockEventBus":
        """设置队列满模式。"""
        self.queue_full = True
        return self

    def with_queue_ok(self) -> "MockEventBus":
        """清除队列满模式。"""
        self.queue_full = False
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    def publish(self, event: Any) -> None:
        """发布事件——兼容 EventBus.publish()。

        非阻塞。queue_full 时静默丢弃。
        """
        self.publish_count += 1

        if self.queue_full:
            self.dropped.append(event)
            self.dropped_count += 1
            return

        self.published.append(event)

        # 通知订阅者（非阻塞）
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> Any:
        """订阅事件——兼容 EventBus.subscribe()。

        阻塞等待下一个事件。
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        self._subscribers.append(q)
        return await q.get()

    # ── 辅助方法 ──────────────────────────────────────────

    @property
    def event_count(self) -> int:
        """已成功发布的事件数。"""
        return len(self.published)

    def get_events_by_type(self, event_type: str) -> list[Any]:
        """按事件类型过滤已发布的事件。

        WHY 便捷方法：测试中最常用的断言模式是"验证某类型事件已发布"。
        """
        return [e for e in self.published if getattr(e, "type", None) == event_type]

    def reset(self) -> None:
        """重置所有状态和追踪。"""
        self.published.clear()
        self.dropped.clear()
        self.publish_count = 0
        self.dropped_count = 0
        self._subscribers.clear()
