"""事件总线：asyncio.Queue 实现发布-订阅。

WHY asyncio.Queue 而非 Redis Pub/Sub：
MVP 单进程足够，零配置零延迟。多进程部署时换实现，接口不变。
"""

from __future__ import annotations

import asyncio

import structlog

from orbit.events.schemas import DashboardEvent

logger = structlog.get_logger()


class EventBus:
    """进程内事件总线。

    调度器 publish（非阻塞），WS 广播协程 subscribe（阻塞等待）。
    WHY 单消费者：一个广播协程消费所有事件，避免多协程重复推送。
    """

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=maxsize)

    def publish(self, event: DashboardEvent) -> None:
        """发布事件（非阻塞）。

        WHY put_nowait：调度器状态转换是同步的，
        阻塞会卡住状态机。队列满时丢弃并警告——
        Dashboard 容忍丢失，不影响数据一致性。
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "EventBus queue full, dropping event",
                type=event.type,
                task_id=event.task_id,
            )

    async def subscribe(self) -> DashboardEvent:
        """异步消费事件（阻塞等待）。

        广播协程调用此方法，无事件时挂起，不占 CPU。
        """
        return await self._queue.get()
