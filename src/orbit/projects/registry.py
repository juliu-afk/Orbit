"""项目注册表 (NL交互 PR #1).

SQLite 存储项目元数据——CRUD + 关键词搜索。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

import structlog

from orbit.projects.models import ProjectRecord

logger = structlog.get_logger("orbit.projects")

DEFAULT_DB_PATH = "data/projects.db"


class ProjectRegistry:
    """项目注册表——管理项目元数据。

    用法:
        reg = ProjectRegistry()
        reg.register("Orbit", repo_url="https://github.com/juliu-afk/Orbit",
                     description="多Agent开发自循环系统",
                     tags=["agent", "python", "llm"])
        projects = reg.search("agent")  # 关键词搜索
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs("data", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._ensure_table()
        return self._conn

    def _ensure_table(self) -> None:
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                repo_url TEXT DEFAULT '',
                description TEXT DEFAULT '',
                issue_tracker TEXT DEFAULT '',
                issue_tracker_config TEXT DEFAULT '{}',
                doc_sources TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self._get_conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active)"
        )

    # ── CRUD ─────────────────────────────────────────────

    def register(
        self, name: str, repo_url: str = "", description: str = "",
        issue_tracker: str = "", issue_tracker_config: dict[str, str] | None = None,
        doc_sources: list[str] | None = None, tags: list[str] | None = None,
    ) -> ProjectRecord:
        """注册新项目或更新已有项目。"""
        conn = self._get_conn()
        now = time.time()
        record = ProjectRecord(
            name=name, repo_url=repo_url, description=description,
            issue_tracker=issue_tracker,
            issue_tracker_config=issue_tracker_config or {},
            doc_sources=doc_sources or [], tags=tags or [],
            is_active=True, created_at=now, updated_at=now,
        )
        conn.execute(
            "INSERT OR REPLACE INTO projects "
            "(name, repo_url, description, issue_tracker, issue_tracker_config, "
            " doc_sources, tags, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (name, repo_url, description, issue_tracker,
             json.dumps(record.issue_tracker_config),
             json.dumps(record.doc_sources), json.dumps(record.tags),
             now, now),
        )
        conn.commit()
        logger.info("project_registered", name=name)
        return record

    def get(self, name: str) -> ProjectRecord | None:
        """按名称查询项目。"""
        row = self._get_conn().execute(
            "SELECT * FROM projects WHERE name=?", (name,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self) -> list[ProjectRecord]:
        """列出所有活跃项目。"""
        rows = self._get_conn().execute(
            "SELECT * FROM projects WHERE is_active=1 ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def deactivate(self, name: str) -> bool:
        """停用项目 (软删除)。"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE projects SET is_active=0, updated_at=? WHERE name=?",
            (time.time(), name),
        )
        conn.commit()
        return conn.total_changes > 0

    # ── 搜索 ─────────────────────────────────────────────

    def search(self, query: str) -> list[ProjectRecord]:
        """关键词搜索——匹配名称/描述/标签。

        排序: 名称精确匹配 > 标签匹配 > 描述包含
        """
        conn = self._get_conn()
        # 简单 LIKE 搜索 (SQLite 无全文索引时用 LIKE)
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM projects WHERE is_active=1 AND "
            "(name LIKE ? OR description LIKE ? OR tags LIKE ?) "
            "ORDER BY updated_at DESC LIMIT 20",
            (pattern, pattern, pattern),
        ).fetchall()
        results = [self._row_to_record(r) for r in rows]
        # 排序: 名称精确匹配优先
        results.sort(key=lambda r: (
            0 if query.lower() in r.name.lower() else 1,
            0 if any(query.lower() in t.lower() for t in r.tags) else 1,
        ))
        return results

    def search_by_tags(self, tags: list[str]) -> list[ProjectRecord]:
        """按标签搜索——任一标签匹配。"""
        conn = self._get_conn()
        results: list[ProjectRecord] = []
        seen: set[str] = set()
        for tag in tags:
            rows = conn.execute(
                "SELECT * FROM projects WHERE is_active=1 AND tags LIKE ? LIMIT 10",
                (f"%{tag}%",),
            ).fetchall()
            for r in rows:
                rec = self._row_to_record(r)
                if rec.name not in seen:
                    seen.add(rec.name)
                    results.append(rec)
        return results

    def count(self) -> int:
        row = self._get_conn().execute(
            "SELECT COUNT(*) as cnt FROM projects WHERE is_active=1"
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 内部 ─────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ProjectRecord:
        def _json_list(raw: str) -> list[Any]:
            try:
                result: Any = json.loads(raw or "[]")
                return result if isinstance(result, list) else []
            except json.JSONDecodeError:
                return []

        def _json_dict(raw: str) -> dict[str, Any]:
            try:
                result: Any = json.loads(raw or "{}")
                return result if isinstance(result, dict) else {}
            except json.JSONDecodeError:
                return {}

        return ProjectRecord(
            name=row["name"],
            repo_url=row["repo_url"] or "",
            description=row["description"] or "",
            issue_tracker=row["issue_tracker"] or "",
            issue_tracker_config=_json_dict(row["issue_tracker_config"]),
            doc_sources=_json_list(row["doc_sources"]),
            tags=_json_list(row["tags"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or 0.0,
            updated_at=row["updated_at"] or 0.0,
        )
