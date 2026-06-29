"""LoopScheduler——Loop 生命周期管理。

管理所有活跃 Loop 的创建/运行/停止/持久化。
每个 Loop 在独立 asyncio 协程中运行。
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from orbit.loop.models import LoopRunner, LoopSchedule
from orbit.loop.parser import CronParser

logger = structlog.get_logger("orbit.loop")


class LoopScheduler:
    """Loop 调度器——管理活跃 Loop 的生命周期。

    Usage:
        scheduler = LoopScheduler(command_executor=meta_orchestrator.run)
        loop = await scheduler.create("5m", "/goal tests pass")
        await scheduler.start(loop.id)
        # ...
        await scheduler.stop(loop.id)
    """

    MAX_LOOPS = 5

    def __init__(self, command_executor: Any = None) -> None:
        self._parser = CronParser()
        self._executor = command_executor
        self._loops: dict[str, LoopRunner] = {}
        self._schedules: dict[str, LoopSchedule] = {}
        self._tasks: dict[str, asyncio.Task] = {}  # P1-NEW2/3: Task 引用用于取消

    async def create(self, interval: str, command: str) -> LoopSchedule:
        """创建 Loop。

        Args:
            interval: 间隔表达式（"5m"/"1h"/"0 9 * * *"）
            command: 执行的命令（如 "/goal tests pass"）

        Returns:
            LoopSchedule

        Raises:
            ValueError: Loop 数量达上限
        """
        if len(self._loops) >= self.MAX_LOOPS:
            raise ValueError(f"Loop 数量已达上限 ({self.MAX_LOOPS})")

        seconds = self._parser.parse(interval)
        loop = LoopSchedule(interval_seconds=seconds, command=command)
        self._schedules[loop.id] = loop

        logger.info("loop_created", loop_id=loop.id, interval=seconds, command=command)
        return loop

    async def start(self, loop_id: str) -> None:
        """启动 Loop——创建异步协程。"""
        if loop_id not in self._schedules:
            raise ValueError(f"Loop {loop_id} 不存在")

        loop = self._schedules[loop_id]
        runner = LoopRunner(loop, self._executor or self._mock_executor)
        self._loops[loop_id] = runner

        # P1-5/P1-NEW2: 后台运行，存 Task 引用用于取消
        task = asyncio.create_task(runner.run())
        task.add_done_callback(self._on_loop_task_done)
        self._tasks[loop_id] = task
        logger.info("loop_started", loop_id=loop_id)

    def _on_loop_task_done(self, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
            if exc:
                logger.error("loop_task_crashed", error=str(exc), exc_info=True)
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass

    async def stop(self, loop_id: str) -> None:
        """停止 Loop。P1-N3: 不存在 ID 报错。"""
        if loop_id not in self._schedules:
            raise ValueError(f"Loop {loop_id} 不存在")
        runner = self._loops.pop(loop_id, None)
        task = self._tasks.pop(loop_id, None)
        if task and not task.done():
            task.cancel()
        if runner:
            runner.stop()
            logger.info("loop_stopped", loop_id=loop_id)
        self._schedules[loop_id].status = "stopped"

    async def pause(self, loop_id: str) -> None:
        """暂停 Loop。P1-N3: 不存在 ID 报错。"""
        if loop_id not in self._schedules:
            raise ValueError(f"Loop {loop_id} 不存在")
        self._schedules[loop_id].status = "paused"
        logger.info("loop_paused", loop_id=loop_id)

    async def resume(self, loop_id: str) -> None:
        """恢复 Loop。P1-N3: 不存在 ID 报错。"""
        if loop_id not in self._schedules:
            raise ValueError(f"Loop {loop_id} 不存在")
        self._schedules[loop_id].status = "active"
        logger.info("loop_resumed", loop_id=loop_id)

    def list_all(self) -> list[LoopSchedule]:
        """列出所有 Loop。"""
        return list(self._schedules.values())

    def get(self, loop_id: str) -> LoopSchedule | None:
        """获取指定 Loop。"""
        return self._schedules.get(loop_id)

    @staticmethod
    async def _mock_executor(command: str) -> dict:
        """Mock 执行器——无 MetaOrchestrator 时的回退。"""
        logger.info("loop_mock_execute", command=command)
        await asyncio.sleep(0.1)
        return {"status": "ok", "command": command}
