"""LoopScheduler——Loop 生命周期管理。

管理所有活跃 Loop 的创建/运行/停止/持久化。
每个 Loop 在独立 asyncio 协程中运行。
Phase 3 收尾: SQLite 持久化——重启后调用 restore_all() 恢复活跃 loop。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

from orbit.loop.models import LoopRunner, LoopSchedule
from orbit.loop.parser import CronParser

logger = structlog.get_logger("orbit.loop")

# P1-3: 绝对路径——不受工作目录变更影响
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "loop_schedules.db"


class LoopScheduler:
    """Loop 调度器——管理活跃 Loop 的生命周期。

    Usage:
        scheduler = LoopScheduler(command_executor=meta_orchestrator.run)
        await scheduler.restore_all()   # Phase 3: 重启后恢复持久化的 loop
        loop = await scheduler.create("5m", "/goal tests pass")
        await scheduler.start(loop.id)
        await scheduler.stop(loop.id)

    SQLite 持久化: loop_schedules 表保存所有 loop 配置+运行时状态。
    调用 restore_all() 自动恢复 status=active 的 loop 协程。
    """

    MAX_LOOPS = 5

    def __init__(self, command_executor: Any = None) -> None:
        self._parser = CronParser()
        self._executor = command_executor
        self._loops: dict[str, LoopRunner] = {}
        self._schedules: dict[str, LoopSchedule] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._db_path = DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._load_all()  # P0-1: 只恢复配置，不自动 start（需显式调用 restore_all）

    # ── DB 层 ──────────────────────────────────────

    def _init_db(self) -> None:
        """创建 loop_schedules 表（幂等）。"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS loop_schedules (
                    id TEXT PRIMARY KEY,
                    interval_seconds INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_run_at TEXT,
                    next_run_at TEXT DEFAULT '',
                    run_count INTEGER DEFAULT 0,
                    last_result_json TEXT,
                    created_at TEXT NOT NULL
                )
            """)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection]:
        """获取 SQLite 连接上下文管理器——WAL 模式。"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _save_sync(self, schedule: LoopSchedule) -> None:
        """同步持久化 LoopSchedule 到 SQLite（upsert）。
        WHY sync: 内部被 asyncio.to_thread 包裹调用——不阻塞 event loop (P0-2)。
        """
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO loop_schedules
                   (id, interval_seconds, command, status, last_run_at,
                    next_run_at, run_count, last_result_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    schedule.id,
                    schedule.interval_seconds,
                    schedule.command,
                    schedule.status,
                    schedule.last_run_at,
                    schedule.next_run_at,
                    schedule.run_count,
                    json.dumps(schedule.last_result) if schedule.last_result else None,
                    schedule.created_at,
                ),
            )

    async def _save(self, schedule: LoopSchedule) -> None:
        """异步持久化——通过 asyncio.to_thread 避免阻塞 event loop (P0-2)。"""
        await asyncio.to_thread(self._save_sync, schedule)

    def _delete(self, loop_id: str) -> None:
        """从 DB 删除 loop。"""
        with self._conn() as conn:
            conn.execute("DELETE FROM loop_schedules WHERE id = ?", (loop_id,))

    def _load_all(self) -> None:
        """从 SQLite 恢复所有未停止的 loop 配置。
        P0-1: 只恢复配置，不自动 start——需显式调用 restore_all()。
        P1-1: 逐条 try/except——单条损坏不阻塞其他 loop 和应用启动。
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM loop_schedules WHERE status != 'stopped'"
            ).fetchall()
        for row in rows:
            try:
                schedule = LoopSchedule(
                    id=row["id"],
                    interval_seconds=row["interval_seconds"],
                    command=row["command"],
                    status=row["status"],
                    last_run_at=row["last_run_at"],
                    next_run_at=row["next_run_at"],
                    run_count=row["run_count"],
                    last_result=(
                        json.loads(row["last_result_json"]) if row["last_result_json"] else None
                    ),
                    created_at=row["created_at"],
                )
                self._schedules[schedule.id] = schedule
                logger.info(
                    "loop_restored", loop_id=schedule.id,
                    command=schedule.command, status=schedule.status,
                )
            except Exception as e:
                logger.error("loop_restore_failed", loop_id=row["id"], error=str(e))

    # ── 公共 API ───────────────────────────────────

    async def restore_all(self) -> int:
        """恢复持久化的活跃 loop——重启后显式调用。
        P0-1: __init__ 只恢复配置，此方法创建 asyncio Task。
        返回恢复启动的数量。
        """
        count = 0
        for schedule in list(self._schedules.values()):
            if schedule.status == "active":
                try:
                    await self.start(schedule.id)
                    count += 1
                except Exception as e:
                    logger.error(
                        "loop_restore_start_failed",
                        loop_id=schedule.id, error=str(e),
                    )
        logger.info("loop_restore_all_done", count=count)
        return count

    async def create(self, interval: str, command: str) -> LoopSchedule:
        """创建 Loop。"""
        # P1-8: 只计非 stopped（active + paused）
        active_count = sum(1 for s in self._schedules.values() if s.status != "stopped")
        if active_count >= self.MAX_LOOPS:
            raise ValueError(f"Loop 数量已达上限 ({self.MAX_LOOPS})")

        seconds = self._parser.parse(interval)
        loop = LoopSchedule(interval_seconds=seconds, command=command)
        self._schedules[loop.id] = loop
        await self._save(loop)

        logger.info("loop_created", loop_id=loop.id, interval=seconds, command=command)
        return loop

    async def start(self, loop_id: str) -> None:
        """启动 Loop——创建异步协程。"""
        if loop_id not in self._schedules:
            raise ValueError(f"Loop {loop_id} 不存在")

        loop = self._schedules[loop_id]
        # P0-2: _persist 创建 asyncio Task——不阻塞 event loop
        runner = LoopRunner(
            loop,
            self._executor or self._mock_executor,
            _persist=lambda: asyncio.ensure_future(self._save(loop)) if loop else None,
        )
        self._loops[loop_id] = runner
        loop.status = "active"
        await self._save(loop)

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
        """停止 Loop。P1-4: await task 等待取消完成。"""
        runner = self._loops.pop(loop_id, None)
        task = self._tasks.pop(loop_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task  # P1-4: 等待 task 完成取消——防止资源泄漏
            except asyncio.CancelledError:
                pass
        if runner:
            runner.stop()
            logger.info("loop_stopped", loop_id=loop_id)
        if loop_id in self._schedules:
            self._schedules[loop_id].status = "stopped"
            await self._save(self._schedules[loop_id])

    async def pause(self, loop_id: str) -> None:
        """暂停 Loop。"""
        if loop_id in self._schedules:
            self._schedules[loop_id].status = "paused"
            await self._save(self._schedules[loop_id])
            logger.info("loop_paused", loop_id=loop_id)

    async def resume(self, loop_id: str) -> None:
        """恢复 Loop。P0-3: 无活跃 task 时重新 start。"""
        if loop_id not in self._schedules:
            return
        self._schedules[loop_id].status = "active"
        await self._save(self._schedules[loop_id])
        # P0-3: pause 后 LoopRunner.run() 退出循环，resume 必须重建 task
        if loop_id not in self._tasks or self._tasks[loop_id].done():
            await self.start(loop_id)
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
