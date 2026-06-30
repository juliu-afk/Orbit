"""Loop 模式数据模型。

P2-4: status 使用 Literal 约束取值范围。
P1-7: import 全部模块级——遵守 PEP 8。
P1-9: next_run_at 在 sleep 前计算——语义正确。
"""

from __future__ import annotations

import asyncio
import structlog
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

logger = structlog.get_logger("orbit.loop")


class LoopSchedule(BaseModel):
    """Loop 调度配置。"""

    id: str = Field(default_factory=lambda: uuid4().hex)
    interval_seconds: int = Field(..., gt=0)
    command: str = Field(..., min_length=1)
    # P2-4: Literal 约束——防止无效状态字符串
    status: Literal["active", "paused", "stopped"] = Field("active")
    last_run_at: str | None = Field(None)
    next_run_at: str = Field("")
    run_count: int = Field(0)
    last_result: dict | None = Field(None)
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


class LoopRunner:
    """Loop 运行器——asyncio 协程。

    _persist: Phase 3——每次 run 后异步持久化 run_count 到 SQLite。
    """

    def __init__(
        self,
        schedule: LoopSchedule,
        callback: callable,
        _persist: callable | None = None,
    ) -> None:
        self.schedule = schedule
        self._callback = callback
        self._persist = _persist  # Phase 3: 每次运行后异步持久化 run_count
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

            # P1-9: next_run_at 在 sleep 之前设置
            self.schedule.next_run_at = (
                datetime.now(UTC) + timedelta(seconds=self.schedule.interval_seconds)
            ).isoformat()

            # Phase 3: 持久化 run_count——每次执行后异步保存
            if self._persist:
                try:
                    self._persist()
                except Exception:
                    # P1-2: 持久化失败记日志——不静默吞掉
                    logger.warning(
                        "loop_persist_failed",
                        loop_id=self.schedule.id,
                        exc_info=True,
                    )

            await asyncio.sleep(self.schedule.interval_seconds)

    def stop(self) -> None:
        self._running = False
        self.schedule.status = "stopped"
