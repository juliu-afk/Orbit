"""审计日志记录器 + 反馈闭环教训库（Step 7.2 AgentOps）。

AuditLogger：封装 structlog，绑定 trace_id/task_id/component，
          输出 JSON 到 stdout（容器日志采集友好）。

LessonStore：SQLite 表 agentops_lessons，存储任务成败教训，
           支持按 domain/task_id 查询。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from orbit.observability.config import agentops_config

logger = structlog.get_logger("orbit.audit")


class AuditLogger:
    """审计日志记录器。

    WHY 封装 structlog 而非直接用：
    统一绑定额外 context（trace_id/component），
    避免各组件手动绑定遗漏字段。

    用法：
        audit = AuditLogger()
        audit.log("scheduler", "task_start", task_id="task-001")
        audit.log("llm_gateway", "llm_call", task_id="task-001",
                  tokens=35, duration_ms=120.5)
    """

    def __init__(self, trace_id: str = "") -> None:
        self._logger = logger.bind(trace_id=trace_id) if trace_id else logger

    def log(
        self,
        component: str,
        operation: str,
        task_id: str = "",
        status: str = "success",
        **kwargs: Any,
    ) -> None:
        """记录审计事件。

        采样控制：agentops_config.AUDIT_SAMPLE_RATE < 1.0 时降采样。
        """
        if not agentops_config.AUDIT_LOG_ENABLED:
            return

        # 采样判断
        if agentops_config.AUDIT_SAMPLE_RATE < 1.0 and (
            (time.time_ns() % 1000) / 1000.0 >= agentops_config.AUDIT_SAMPLE_RATE
        ):
            return

        self._logger.info(
            "audit_event",
            component=component,
            operation=operation,
            task_id=task_id,
            status=status,
            **kwargs,
        )


# ── 教训库 ────────────────────────────────────────────────


@dataclass
class Lesson:
    """一条教训记录。"""

    task_id: str
    domain: str  # 领域：scheduler | llm | sandbox | graph | hallucination
    outcome: Literal["success", "failure"]
    lesson: str
    tags: list[str] = field(default_factory=list)
    lesson_id: int = 0
    created_at: str = ""


class LessonStore:
    """教训库——SQLite 存储，支持按领域/任务/标签查询。

    WHY SQLite 而非 PostgreSQL：
    - 教训数据量小（每日 <100 条），SQLite 完全够用
    - 零配置，与 KnowledgeStore 共用 data/ 目录
    - 需要 PostgreSQL 时迁移成本低（1 张表，无外键）
    """

    def __init__(self, db_path: str = "data/lessons.db") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            import os

            os.makedirs("data", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._ensure_table()
        return self._conn

    def _ensure_table(self) -> None:
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS agentops_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('success','failure')),
                lesson TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """)
        self._get_conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_domain ON agentops_lessons(domain)"
        )
        self._get_conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_lessons_task_id ON agentops_lessons(task_id)"
        )

    def add(
        self,
        task_id: str,
        domain: str,
        outcome: Literal["success", "failure"],
        lesson: str,
        tags: list[str] | None = None,
    ) -> Lesson:
        """记录一条教训。"""
        if not agentops_config.LESSON_STORE_ENABLED:
            return Lesson(task_id=task_id, domain=domain, outcome=outcome, lesson=lesson)

        conn = self._get_conn()
        tags_str = ",".join(tags) if tags else ""
        cursor = conn.execute(
            "INSERT INTO agentops_lessons (task_id, domain, outcome, lesson, tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, domain, outcome, lesson, tags_str),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM agentops_lessons WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return (
            self._row_to_lesson(row)
            if row
            else Lesson(task_id=task_id, domain=domain, outcome=outcome, lesson=lesson)
        )

    def list_by_domain(self, domain: str, limit: int = 50) -> list[Lesson]:
        """按领域查询教训。"""
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM agentops_lessons WHERE domain = ? ORDER BY created_at DESC LIMIT ?",
                (domain, limit),
            )
            .fetchall()
        )
        return [self._row_to_lesson(r) for r in rows]

    def list_by_task(self, task_id: str) -> list[Lesson]:
        """按任务查询教训。"""
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM agentops_lessons WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            )
            .fetchall()
        )
        return [self._row_to_lesson(r) for r in rows]

    def count(self) -> int:
        """教训总数。"""
        row = self._get_conn().execute("SELECT COUNT(*) as cnt FROM agentops_lessons").fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_lesson(row: sqlite3.Row) -> Lesson:
        tags_raw = row["tags"] or ""
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        return Lesson(
            lesson_id=row["id"],
            task_id=row["task_id"],
            domain=row["domain"],
            outcome=row["outcome"],
            lesson=row["lesson"],
            tags=tags,
            created_at=row["created_at"],
        )
