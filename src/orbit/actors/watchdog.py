"""ActorWatchdog——stale actor 检测与清理。

对标 MiMo Code actor/registry.ts stale 检测。
每 60 秒扫描——status=pending/running 但 updated_at >5min → zombie → 清理。
"""

from __future__ import annotations

import asyncio

import structlog

from orbit.actors.registry import ActorRegistry

logger = structlog.get_logger()

STALE_SECONDS = 300  # 5 分钟——对标 MiMo
SCAN_INTERVAL = 60  # 60 秒扫描间隔


class ActorWatchdog:
    """后台协程——stale actor 检测 + zombie 清理。

    Usage:
        watchdog = ActorWatchdog(registry)
        asyncio.create_task(watchdog.run())
    """

    def __init__(self, registry: ActorRegistry, stale_seconds: int = STALE_SECONDS) -> None:
        self.registry = registry
        self.stale_seconds = stale_seconds
        self._running = False

    async def run(self) -> None:
        """后台循环——每 60s 扫描一次。"""
        self._running = True
        logger.info("watchdog_started", interval_s=SCAN_INTERVAL, stale_s=self.stale_seconds)
        while self._running:
            try:
                await self._scan()
            except (OSError, RuntimeError, ValueError) as e:
                # OSError: SQLite I/O 错误
                # RuntimeError: 数据库连接异常
                # ValueError: 参数校验失败
                logger.error("watchdog_scan_failed", error=str(e), exc_info=True)
            await asyncio.sleep(SCAN_INTERVAL)

    async def stop(self) -> None:
        """停止 watchdog。"""
        self._running = False

    async def _scan(self) -> None:
        """单次扫描——查找 stale actor → mark zombie → delete。"""
        stale = self.registry.find_stale(self.stale_seconds)
        if not stale:
            return
        for actor in stale:
            logger.warning(
                "actor_stale_detected",
                actor_id=actor.actor_id,
                role=actor.role,
                status=actor.status.value,
                seconds_since_update=(
                    __import__("datetime").datetime.now(__import__("datetime").UTC)
                    - actor.updated_at
                ).total_seconds(),
            )
            self.registry.mark_zombie(actor.actor_id)
            self.registry.delete(actor.actor_id)
        logger.info("watchdog_cleanup_done", stale_count=len(stale))
