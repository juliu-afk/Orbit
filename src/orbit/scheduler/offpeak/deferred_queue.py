"""DeferredQueue——SQLite 持久化延迟执行队列。

从 offpeak_scheduler.py 拆分。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import cast, get_args

import structlog

from orbit.scheduler.offpeak_models import DeferredStatus, DeferredTask, EnqueueResult

logger = structlog.get_logger("orbit.offpeak")


# ── DeferredQueue ──────────────────────────────────────────────

class DeferredQueue:
    """延迟执行队列——SQLite 持久化。

    WHY raw sqlite3: 遵循 LoopScheduler/SessionRegistry 的已有模式。
    没有 async ORM 的历史包袱。所有写操作由 asyncio.Lock 保护。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    # ── 公共 API ──

    async def push(self, task: DeferredTask) -> int:
        """入队——返回队列位置（同窗口内排第几）。"""
        async with self._lock:
            return await asyncio.to_thread(self._push_sync, task)

    async def pop_for_window(
        self, window_start: str, window_end: str, limit: int
    ) -> list[DeferredTask]:
        """取出指定窗口内的排队任务——按优先级+预估耗时排序。

        取出的任务 status 由 queued → released 前端不直接调 orch.run()，
        调用方负责 mark_released→执行→mark_done。
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._pop_for_window_sync, window_start, window_end, limit
            )

    async def list_all(self, status_filter: str | None = None) -> list[DeferredTask]:
        """列出排队任务——供 API 和 watcher 使用。"""
        async with self._lock:
            return await asyncio.to_thread(self._list_all_sync, status_filter)

    async def promote_to_urgent(self, goal_id: str) -> DeferredTask | None:
        """将排队任务提升为立即执行——返回 task 供调用方直接 orch.run()。

        状态: queued → urgent_override
        """
        async with self._lock:
            return await asyncio.to_thread(self._promote_sync, goal_id)

    async def mark_released(self, goal_id: str) -> None:
        """标记任务已释放到执行器。queued → released。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_released_sync, goal_id)

    async def mark_done(
        self, goal_id: str, actual_tokens: int, cost_saved: float
    ) -> None:
        """标记任务完成 + 记录实际消耗和节省金额。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_done_sync, goal_id, actual_tokens, cost_saved)

    async def mark_cancelled(self, goal_id: str) -> None:
        """取消排队中的任务。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_cancelled_sync, goal_id)

    async def get_savings_report(self) -> dict:
        """查询成本节省统计——供 savings-report API。"""
        async with self._lock:
            return await asyncio.to_thread(self._savings_report_sync)

    async def reschedule(
        self, goal_id: str, new_window_start: str, new_window_end: str
    ) -> None:
        """将任务重新调度到另一个窗口——窗口溢出时用。"""
        async with self._lock:
            await asyncio.to_thread(
                self._reschedule_sync, goal_id, new_window_start, new_window_end
            )

    # ── 同步内部实现 ──

    def _connect(self) -> sqlite3.Connection:
        """每次操作创建新连接——线程安全，遵循 LoopScheduler 模式。"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deferred_tasks (
                    id TEXT PRIMARY KEY,
                    goal_description TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'NORMAL',
                    provider TEXT NOT NULL DEFAULT '',
                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_duration_seconds INTEGER NOT NULL DEFAULT 0,
                    target_window_start TEXT NOT NULL DEFAULT '',
                    target_window_end TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    released_at TEXT,
                    completed_at TEXT,
                    actual_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_saved_yuan REAL NOT NULL DEFAULT 0.0,
                    goal_json TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_status ON deferred_tasks(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_window ON deferred_tasks(target_window_start, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_provider ON deferred_tasks(provider, status)"
            )
            conn.commit()

    def _push_sync(self, task: DeferredTask) -> int:
        now_iso = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO deferred_tasks
                   (id, goal_description, priority, provider, estimated_tokens,
                    estimated_duration_seconds, target_window_start, target_window_end,
                    status, created_at, goal_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)""",
                (
                    task.id, task.goal_description, task.priority, task.provider,
                    task.estimated_tokens, task.estimated_duration_seconds,
                    task.target_window_start, task.target_window_end,
                    now_iso, task.goal_json,
                ),
            )
            conn.commit()

            # 计算同窗口内的位置——同一连接内查询，保证一致性
            count_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM deferred_tasks WHERE status='queued'"
                " AND target_window_start = ?",
                (task.target_window_start,),
            ).fetchone()
            return count_row["cnt"] if count_row else 0

    def _pop_for_window_sync(
        self, window_start: str, window_end: str, limit: int
    ) -> list[DeferredTask]:
        with self._connect() as conn:
            # 按优先级排序: CRITICAL < HIGH < NORMAL < LOW，同优先级按预估耗时升序
            rows = conn.execute(
                """SELECT * FROM deferred_tasks
                   WHERE status = 'queued'
                     AND target_window_start = ?
                   ORDER BY
                     CASE priority
                       WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                       WHEN 'NORMAL' THEN 2 WHEN 'LOW' THEN 3
                       ELSE 3 END,
                     estimated_duration_seconds ASC
                   LIMIT ?""",
                (window_start, limit),
            ).fetchall()

            tasks = []
            for row in rows:
                # 先标记为 released
                conn.execute(
                    "UPDATE deferred_tasks SET status='released', released_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), row["id"]),
                )
                tasks.append(self._row_to_task(row))
            conn.commit()
            return tasks

    def _list_all_sync(self, status_filter: str | None = None) -> list[DeferredTask]:
        with self._connect() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM deferred_tasks WHERE status = ? ORDER BY created_at ASC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM deferred_tasks ORDER BY created_at ASC"
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def _promote_sync(self, goal_id: str) -> DeferredTask | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM deferred_tasks WHERE id = ? AND status = 'queued'",
                (goal_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE deferred_tasks SET status='urgent_override', released_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), goal_id),
            )
            conn.commit()
            return self._row_to_task(row)

    def _mark_released_sync(self, goal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE deferred_tasks SET status='released', released_at=? WHERE id=? AND status='queued'",
                (datetime.now(UTC).isoformat(), goal_id),
            )
            conn.commit()

    def _mark_done_sync(
        self, goal_id: str, actual_tokens: int, cost_saved: float
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE deferred_tasks
                   SET status='done', completed_at=?, actual_tokens=?, cost_saved_yuan=?
                   WHERE id=?""",
                (datetime.now(UTC).isoformat(), actual_tokens, cost_saved, goal_id),
            )
            conn.commit()

    def _mark_cancelled_sync(self, goal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE deferred_tasks SET status='cancelled' WHERE id=? AND status='queued'",
                (goal_id,),
            )
            conn.commit()

    def _savings_report_sync(self) -> dict:
        with self._connect() as conn:
            # 已完成任务统计
            total_row = conn.execute(
                """SELECT COUNT(*) as cnt, SUM(actual_tokens) as tokens,
                          SUM(cost_saved_yuan) as saved
                   FROM deferred_tasks WHERE status = 'done'"""
            ).fetchone()

            # 按厂商分拆
            by_provider_rows = conn.execute(
                """SELECT provider, COUNT(*) as cnt, SUM(actual_tokens) as tokens,
                          SUM(cost_saved_yuan) as saved
                   FROM deferred_tasks WHERE status = 'done'
                   GROUP BY provider"""
            ).fetchall()

            # 队列中的
            queued_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM deferred_tasks WHERE status = 'queued'"
            ).fetchone()

            return {
                "total_tasks_deferred": (total_row["cnt"] or 0) + (queued_count["cnt"] or 0),
                "total_tasks_done": total_row["cnt"] or 0,
                "total_tasks_queued": queued_count["cnt"] or 0,
                "total_tokens_offpeak": total_row["tokens"] or 0,
                "total_saved_yuan": round(total_row["saved"] or 0.0, 2),
                "by_provider": [
                    {
                        "provider": r["provider"],
                        "tasks": r["cnt"],
                        "tokens": r["tokens"] or 0,
                        "saved_yuan": round(r["saved"] or 0.0, 2),
                    }
                    for r in by_provider_rows
                ],
            }

    def _reschedule_sync(
        self, goal_id: str, new_window_start: str, new_window_end: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE deferred_tasks
                   SET target_window_start=?, target_window_end=?
                   WHERE id=? AND status='queued'""",
                (new_window_start, new_window_end, goal_id),
            )
            conn.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> DeferredTask:
        assert row["status"] in get_args(DeferredStatus), f"无效 DeferredStatus: {row['status']}"
        return DeferredTask(
            id=row["id"],
            goal_description=row["goal_description"],
            priority=row["priority"],
            provider=row["provider"],
            estimated_tokens=row["estimated_tokens"],
            estimated_duration_seconds=row["estimated_duration_seconds"],
            target_window_start=row["target_window_start"],
            target_window_end=row["target_window_end"],
            status=cast(DeferredStatus, row["status"]),
            created_at=row["created_at"],
            released_at=row["released_at"],
            completed_at=row["completed_at"],
            actual_tokens=row["actual_tokens"],
            cost_saved_yuan=row["cost_saved_yuan"],
            goal_json=row["goal_json"],
        )


