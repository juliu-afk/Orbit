"""Loop 模式数据模型。"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class LoopSchedule(BaseModel):
    """Loop 调度配置。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    interval_seconds: int = Field(..., gt=0)
    command: str = Field(..., min_length=1)
    status: str = Field("active")  # active|paused|stopped
    last_run_at: str | None = Field(None)
    next_run_at: str = Field("")
    run_count: int = Field(0)
    last_result: dict | None = Field(None)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


class LoopRunner:
    """Loop 运行器——asyncio 协程。"""

    def __init__(self, schedule: LoopSchedule, callback: callable) -> None:
        self.schedule = schedule
        self._callback = callback
        self._running = False
        self._task = None

    async def run(self) -> None:
        """Loop 主循环。"""
        self._running = True
        while self._running and self.schedule.status == "active":
            try:
                now = datetime.now(UTC).isoformat()
                self.schedule.last_run_at = now
                self.schedule.run_count += 1

                result = await self._callback(self.schedule.command)
                self.schedule.last_result = {
                    "status": "ok" if result else "error",
                    "run_at": now,
                }
            except Exception as e:
                self.schedule.last_result = {
                    "status": "error",
                    "error": str(e),
                    "run_at": datetime.now(UTC).isoformat(),
                }

            # 计算下次触发时间
            await asyncio.sleep(self.schedule.interval_seconds)
            self.schedule.next_run_at = datetime.now(UTC).isoformat()

    def stop(self) -> None:
        self._running = False
        self.schedule.status = "stopped"
