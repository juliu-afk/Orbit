"""Session + ChatMessage 注册表 (Session PR #1).

SQLite 持久化——与 ProjectRegistry 共用 `data/orbit.db`。
表: sessions, chat_messages
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
import uuid
from typing import Any

import structlog

from orbit.sessions.models import ChatMessageRecord, SessionRecord

logger = structlog.get_logger("orbit.sessions")

# WHY ORBIT_HOME: exe 的 CWD 是项目根目录而非 exe 所在目录，相对路径会指错 DB
_ORBIT_HOME = os.environ.get("ORBIT_HOME", os.getcwd())
DEFAULT_DB_PATH = os.path.join(_ORBIT_HOME, "data", "projects.db")


class SessionRegistry:
    """Session + ChatMessage 持久化注册表。

    用法:
        reg = SessionRegistry()
        s = reg.create("Code-Insight-Financial", title="修复导入")
        msgs = reg.get_messages(s.session_id)
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._locks: dict[str, object] = {}  # V16.0 Phase A: 会话级并发锁

    def get_session_lock(self, session_id: str) -> object:
        """V16.0 Phase A: 会话级锁——同session串行处理消息。"""
        import asyncio
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def update_message(self, msg_id: int, **kwargs) -> None:
        """V16.0 Phase A: 更新消息——占位→已发送, 或更新content/status。"""
        conn = self._get_conn()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(
            f"UPDATE chat_messages SET {sets} WHERE id=?",
            (*kwargs.values(), msg_id),
        )
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs("data", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        conn = self._get_conn()
        # sessions 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                title TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (project_name) REFERENCES projects(name) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)")
        # Phase 2: parent-child fork tracking
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE sessions ADD COLUMN parent_session_id TEXT DEFAULT NULL")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE sessions ADD COLUMN lineage_reason TEXT DEFAULT NULL")
        # Session PR #2: local_path 持久化——避免每次读都 JOIN projects 表
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE sessions ADD COLUMN local_path TEXT DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id)"
        )
        # chat_messages 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                candidates TEXT DEFAULT '[]',
                cross_project_warning TEXT DEFAULT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(session_id, created_at)"
        )
        # V16.0 Phase A: 消息持久化——status + parts + structured_output
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE chat_messages ADD COLUMN status TEXT DEFAULT 'sent'")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE chat_messages ADD COLUMN parts TEXT DEFAULT '[]'")
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE chat_messages ADD COLUMN structured_output TEXT DEFAULT ''")
        # V15.3: session_summaries — 跨 session 长期记忆（US4）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                key_points TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_summaries_session ON session_summaries(session_id)"
        )
        # V15.3: grill_log — Grilling 反馈数据（US7）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grill_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                asking_agent TEXT NOT NULL,
                answering_agent TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                question_json TEXT NOT NULL,
                answer_text TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_grill_task ON grill_log(task_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_grill_hash ON grill_log(question_hash)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_grill_dedup ON grill_log(task_id, question_hash)"
        )
        conn.commit()

    # ── Session CRUD ───────────────────────────────────

    def create(self, project_name: str, title: str = "", local_path: str = "") -> SessionRecord:
        """创建新 Session。返回带 UUID 的 SessionRecord。"""
        conn = self._get_conn()
        now = time.time()
        session_id = uuid.uuid4().hex  # 32 chars, no dashes
        # WHY 去连字符: 与 TaskStatusResponse.task_id 格式一致，方便前端统一处理
        conn.execute(
            "INSERT INTO sessions (id, project_name, title, status, created_at, updated_at, local_path) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (session_id, project_name, title, now, now, local_path),
        )
        conn.commit()
        logger.info("session_created", session_id=session_id, project=project_name, path=local_path)
        return SessionRecord(
            session_id=session_id,
            project_name=project_name,
            local_path=local_path,
            title=title,
            status="active",
            created_at=now,
            updated_at=now,
        )

    # WHY COALESCE: 优先用 sessions 表自己的 local_path（新），回退到 projects 表（旧数据兼容）
    # WHY effective_path 别名: 避免与 s.* 中 local_path 列名冲突导致 row["local_path"] 取到空值
    _SELECT_SQL = (
        "SELECT s.*, COALESCE(NULLIF(s.local_path, ''), p.local_path, '') as effective_path "
        "FROM sessions s "
        "LEFT JOIN projects p ON s.project_name = p.name "
    )

    def get(self, session_id: str) -> SessionRecord | None:
        """按 ID 查询 Session。"""
        row = (
            self._get_conn()
            .execute(self._SELECT_SQL + "WHERE s.id=?", (session_id,))
            .fetchone()
        )
        return self._row_to_session(row) if row else None

    def list_all(self, status: str | None = None) -> list[SessionRecord]:
        """列出所有 Session，按 updated_at DESC。可选过滤 status。"""
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                self._SELECT_SQL + "WHERE s.status=? ORDER BY s.updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(self._SELECT_SQL + "ORDER BY s.updated_at DESC").fetchall()
        return [self._row_to_session(r) for r in rows]

    def list_by_project(self, project_name: str) -> list[SessionRecord]:
        """列出某项目的所有 Session。"""
        rows = (
            self._get_conn()
            .execute(
                self._SELECT_SQL + "WHERE s.project_name=? ORDER BY s.updated_at DESC",
                (project_name,),
            )
            .fetchall()
        )
        return [self._row_to_session(r) for r in rows]

    def update(self, session_id: str, **kwargs: Any) -> SessionRecord | None:
        """更新 Session 字段（title / status）+ touch updated_at。

        Raises:
            ValueError: 尝试将 archived session 改回 active。

        WHY 终态不可逆：archived 后不可改回 active。抛错而非静默覆盖，
        调用方（API 层）可将 ValueError 转为 409 Conflict 响应。
        """
        rec = self.get(session_id)
        if rec is None:
            return None

        # 终态检查
        if "status" in kwargs and rec.status == "archived" and kwargs["status"] != "archived":
            raise ValueError(f"Session {session_id} 已归档，不可恢复为活跃状态")

        now = time.time()
        new_title = kwargs.get("title", rec.title)
        new_status = kwargs.get("status", rec.status)

        # WHY 显式列名而非 f-string: bandit B608 标记任何拼接 SQL。
        # 只有 2 个可更新列，分支写更安全。
        conn = self._get_conn()
        conn.execute(
            "UPDATE sessions SET title=?, status=?, updated_at=? WHERE id=?",
            (new_title, new_status, now, session_id),
        )
        conn.commit()
        return self.get(session_id)

    def touch(self, session_id: str) -> None:
        """仅刷新 updated_at（聊天活动触发）。"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?",
            (time.time(), session_id),
        )
        conn.commit()

    def archive(self, session_id: str) -> bool:
        """归档 Session（终态操作）。"""
        return self.update(session_id, status="archived") is not None

    # ── ChatMessage CRUD ───────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        candidates: list[dict[str, Any]] | None = None,
        cross_project_warning: str | None = None,
        status: str = "sent",
        parts: list[dict[str, Any]] | None = None,
        structured_output: str = "",
    ) -> ChatMessageRecord:
        """添加一条聊天消息——V16.0: role统一为assistant, 返回自增ID。

        status: "pending"(占位) | "sent"(已送达) | "error"(发送失败)
        """
        # V16.0 Phase A: role统一——agent→assistant
        if role == "agent":
            role = "assistant"
        conn = self._get_conn()
        now = time.time()
        cursor = conn.execute(
            "INSERT INTO chat_messages "
            "(session_id, role, content, candidates, cross_project_warning, created_at, status, parts, structured_output) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(candidates or []),
                cross_project_warning,
                now,
                status,
                json.dumps(parts or []),
                structured_output,
            ),
        )
        conn.commit()
        msg_id = cursor.lastrowid
        return ChatMessageRecord(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            candidates=candidates or [],
            cross_project_warning=cross_project_warning,
            created_at=now,
        )

    def get_messages(self, session_id: str, limit: int = 200) -> list[ChatMessageRecord]:
        """获取会话消息——V16.0: 默认200条安全网，传0=无上限(token预算驱动)。"""
        """获取 Session 的最近 N 条消息。"""
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM chat_messages WHERE session_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            )
            .fetchall()
        )
        # 按时间正序返回（最旧 → 最新）
        return [self._row_to_message(r) for r in reversed(rows)]

    # ── Phase 2: FTS5 + Fork ──────────────────────────

    def enable_fts(self) -> bool:
        """启用 FTS5 全文搜索（幂等）."""
        from orbit.sessions.fts import setup_session_fts

        conn = self._get_conn()
        return setup_session_fts(conn)

    def fts_search(
        self,
        query: str,
        session_filter: str | None = None,
        role_filter: str | None = None,
        limit: int = 20,
    ) -> list:
        """FTS5 全文搜索聊天消息."""
        from orbit.sessions.fts import search_messages

        conn = self._get_conn()
        return search_messages(conn, query, session_filter, role_filter, limit)

    def create_fork(self, parent_session_id: str, reason: str = "") -> str:
        """创建子 Session 分叉——记录 parent-child lineage."""
        parent = self.get(parent_session_id)
        project = parent.project_name if parent else "unknown"
        title = f"Fork of {parent_session_id[:8]}"
        # P2-1: 复制父会话的 local_path，否则 fork 后文件树等功能失效
        child = self.create(project, title=title, local_path=parent.local_path if parent else "")

        conn = self._get_conn()
        conn.execute(
            "UPDATE sessions SET parent_session_id=?, lineage_reason=? WHERE id=?",
            (parent_session_id, reason, child.session_id),
        )
        conn.commit()
        logger.info(
            "session_forked",
            parent=parent_session_id[:8],
            child=child.session_id[:8],
            reason=reason,
        )
        return child.session_id

    def get_child_sessions(self, session_id: str) -> list[SessionRecord]:
        """获取指定 Session 的所有子 Session."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT s.*, p.local_path "
            "FROM sessions s LEFT JOIN projects p ON s.project_name = p.name "
            "WHERE s.parent_session_id=? ORDER BY s.created_at",
            (session_id,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 内部 ───────────────────────────────────────────

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionRecord:
        # WHY effective_path: COALESCE 结果，避免与 s.* 中 local_path 列名冲突
        lp = (row["effective_path"] or "") if "effective_path" in row.keys() else (row["local_path"] or "")
        return SessionRecord(
            session_id=row["id"],
            project_name=row["project_name"] or "",
            local_path=lp,
            title=row["title"] or "",
            status=row["status"] or "active",
            created_at=row["created_at"] or 0.0,
            updated_at=row["updated_at"] or 0.0,
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ChatMessageRecord:
        def _json_list(raw: str) -> list[dict[str, Any]]:
            try:
                result: Any = json.loads(raw or "[]")
                return result if isinstance(result, list) else []
            except json.JSONDecodeError:
                return []

        return ChatMessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            candidates=_json_list(row["candidates"]),
            cross_project_warning=row["cross_project_warning"] or None,
            created_at=row["created_at"] or 0.0,
        )
