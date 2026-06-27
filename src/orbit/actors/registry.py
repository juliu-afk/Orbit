"""ActorRegistry——SQLite 支持的子Agent 状态机。

对标 MiMo Code actor/registry.ts ~300行。
WHY SQLite: 零配置、WAL 并发安全、子Agent 生命周期短暂。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

import structlog

from orbit.actors.models import ActorOutcome, ActorRecord, ActorStatus

logger = structlog.get_logger()

DB_PATH = Path("data/actor_registry.db")


class ActorRegistry:
    """子Agent 注册表——CRUD + 状态机。

    SQLite 表结构:
        actor_id TEXT PRIMARY KEY,
        parent_task_id TEXT,
        role TEXT,
        task TEXT,
        status TEXT DEFAULT 'pending',
        outcome TEXT,
        result_json TEXT,
        error TEXT,
        created_at TEXT,
        updated_at TEXT,
        session_id TEXT
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DB_PATH
        self._is_memory = str(self._db_path) == ":memory:"
        if not self._is_memory:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # :memory: 需要持久连接（否则每连接新建 DB）
        self._persistent_conn: sqlite3.Connection | None = None
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接——:memory: 复用持久连接，文件模式每次新建并关闭."""
        if self._is_memory:
            if self._persistent_conn is None:
                self._persistent_conn = sqlite3.connect(":memory:")
                self._persistent_conn.row_factory = sqlite3.Row
            yield self._persistent_conn
        else:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                yield conn
            finally:
                conn.close()

    def _init_db(self) -> None:
        """创建表和索引（幂等）。"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS actor_registry (
                    actor_id TEXT PRIMARY KEY,
                    parent_task_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    task TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    outcome TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    session_id TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_actor_status ON actor_registry(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_actor_parent ON actor_registry(parent_task_id)"
            )

    def allocate(self, parent_task_id: str = "") -> str:
        """分配 actor ID。总是返回新 ID——不碰撞。"""
        return uuid.uuid4().hex[:12]

    def register(self, record: ActorRecord) -> None:
        """注册新 actor（status=pending）。"""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO actor_registry
                   (actor_id, parent_task_id, role, task, status, created_at, updated_at, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.actor_id, record.parent_task_id, record.role, record.task,
                 ActorStatus.PENDING.value, now, now, record.session_id),
            )

    def update_status(
        self,
        actor_id: str,
        status: ActorStatus,
        outcome: ActorOutcome | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """更新 actor 状态——对标 MiMo runTurn cleanup."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """UPDATE actor_registry
                   SET status = ?, outcome = ?, result_json = ?, error = ?, updated_at = ?
                   WHERE actor_id = ?""",
                (status.value, outcome.value if outcome else None,
                 json.dumps(result) if result else None, error, now, actor_id),
            )

    def get(self, actor_id: str) -> ActorRecord | None:
        """查询单个 actor。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM actor_registry WHERE actor_id = ?", (actor_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def get_by_parent(self, parent_task_id: str) -> list[ActorRecord]:
        """按父任务查询所有子Actor。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM actor_registry WHERE parent_task_id = ? ORDER BY created_at",
                (parent_task_id,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def list_active(self) -> list[ActorRecord]:
        """列出所有活跃 actor（pending + running）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM actor_registry WHERE status IN ('pending', 'running') ORDER BY created_at"
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def count_active(self) -> int:
        """活跃 actor 数量——用于并发限制检查。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM actor_registry WHERE status IN ('pending', 'running')"
            ).fetchone()
            return row["cnt"]

    def find_stale(self, stale_seconds: int = 300) -> list[ActorRecord]:
        """查找 stale actor（updated_at 超过 stal_seconds 秒未更新）。"""
        threshold = datetime.now(UTC).timestamp() - stale_seconds
        threshold_str = datetime.fromtimestamp(threshold, tz=UTC).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM actor_registry WHERE status IN ('pending', 'running') AND updated_at < ?",
                (threshold_str,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def mark_zombie(self, actor_id: str) -> None:
        """标记 actor 为 zombie。"""
        self.update_status(actor_id, ActorStatus.ZOMBIE, error="stale timeout")

    def delete(self, actor_id: str) -> None:
        """删除 actor 记录（zombie 清理）。"""
        with self._conn() as conn:
            conn.execute("DELETE FROM actor_registry WHERE actor_id = ?", (actor_id,))

    # ── 内部 ─────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> ActorRecord:
        result = None
        if row["result_json"]:
            with suppress(json.JSONDecodeError):
                result = json.loads(row["result_json"])

        return ActorRecord(
            actor_id=row["actor_id"],
            parent_task_id=row["parent_task_id"] or "",
            role=row["role"] or "",
            task=row["task"] or "",
            status=ActorStatus(row["status"]),
            outcome=ActorOutcome(row["outcome"]) if row["outcome"] else None,
            result=result,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            session_id=row["session_id"],
        )
