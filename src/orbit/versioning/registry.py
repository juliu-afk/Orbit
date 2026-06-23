"""版本注册表 (Step 7.4/7.5 PR #2).

SQLite 存储版本历史 + Schema 迁移记录 + 发布审计事件。
用途: 运维查询"当前版本是什么？""上次发布是什么时候？""哪些迁移已应用？"
"""

from __future__ import annotations

import sqlite3
import time

import structlog

from orbit.versioning.models import MigrationRecord, ReleaseEvent, VersionRecord

logger = structlog.get_logger("orbit.versioning")

DEFAULT_DB_PATH = "data/versioning.db"


class VersionRegistry:
    """版本注册表——版本追踪 + 迁移管理 + 发布审计。

    用法:
        reg = VersionRegistry()
        reg.install_version("v0.15.0", "新增备份管理器")
        reg.record_migration("V001", "v0.1.0", checksum="abc123")
        reg.record_release("deploy", "v0.15.0", trigger="manual")
        print(reg.current_version())  # "v0.15.0"
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            import os

            os.makedirs("data", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                version TEXT PRIMARY KEY,
                installed_at REAL NOT NULL,
                description TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                migration_id TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                applied_at REAL NOT NULL,
                checksum TEXT DEFAULT '',
                success INTEGER DEFAULT 1,
                error_message TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS release_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                version TEXT NOT NULL,
                previous_version TEXT DEFAULT '',
                traffic_ratio REAL DEFAULT 0.0,
                trigger TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                success INTEGER DEFAULT 1,
                details TEXT DEFAULT ''
            )
        """)
        conn.commit()

    # ── 版本管理 ──────────────────────────────────────────

    def install_version(self, version: str, description: str = "") -> VersionRecord:
        """记录新版本安装。

        自动将之前的活跃版本标记为非活跃。
        """
        conn = self._get_conn()
        now = time.time()
        # 将当前活跃版本标记为非活跃
        conn.execute("UPDATE versions SET is_active=0 WHERE is_active=1")
        conn.execute(
            "INSERT OR REPLACE INTO versions (version, installed_at, description, is_active) "
            "VALUES (?, ?, ?, 1)",
            (version, now, description),
        )
        conn.commit()
        logger.info("version_installed", version=version, description=description)
        return VersionRecord(
            version=version, installed_at=now, description=description, is_active=True
        )

    def current_version(self) -> str | None:
        """返回当前活跃版本号。"""
        row = (
            self._get_conn()
            .execute(
                "SELECT version FROM versions WHERE is_active=1 ORDER BY installed_at DESC LIMIT 1"
            )
            .fetchone()
        )
        return row["version"] if row else None

    def list_versions(self, limit: int = 20) -> list[VersionRecord]:
        """列出最近安装的版本。"""
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM versions ORDER BY installed_at DESC, version DESC LIMIT ?", (limit,)
            )
            .fetchall()
        )
        return [
            VersionRecord(
                version=r["version"],
                installed_at=r["installed_at"],
                description=r["description"] or "",
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    # ── 迁移管理 ──────────────────────────────────────────

    def record_migration(
        self,
        migration_id: str,
        version: str,
        checksum: str = "",
        success: bool = True,
        error_message: str = "",
    ) -> MigrationRecord:
        """记录 Schema 迁移。"""
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO migrations "
            "(migration_id, version, applied_at, checksum, success, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (migration_id, version, now, checksum, int(success), error_message),
        )
        conn.commit()
        logger.info("migration_recorded", migration_id=migration_id, success=success)
        return MigrationRecord(
            migration_id=migration_id,
            version=version,
            applied_at=now,
            checksum=checksum,
            success=success,
            error_message=error_message,
        )

    def list_migrations(self) -> list[MigrationRecord]:
        """列出所有迁移记录。"""
        rows = (
            self._get_conn().execute("SELECT * FROM migrations ORDER BY applied_at ASC").fetchall()
        )
        return [
            MigrationRecord(
                migration_id=r["migration_id"],
                version=r["version"],
                applied_at=r["applied_at"],
                checksum=r["checksum"] or "",
                success=bool(r["success"]),
                error_message=r["error_message"] or "",
            )
            for r in rows
        ]

    def is_migration_applied(self, migration_id: str) -> bool:
        """检查迁移是否已应用。"""
        row = (
            self._get_conn()
            .execute("SELECT 1 FROM migrations WHERE migration_id=? AND success=1", (migration_id,))
            .fetchone()
        )
        return row is not None

    # ── 发布审计 ──────────────────────────────────────────

    def record_release(
        self,
        event_type: str,
        version: str,
        previous_version: str = "",
        traffic_ratio: float = 0.0,
        trigger: str = "manual",
        success: bool = True,
        details: str = "",
    ) -> ReleaseEvent:
        """记录发布/回滚事件。"""
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "INSERT INTO release_events "
            "(event_type, version, previous_version, traffic_ratio, trigger, timestamp, success, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_type,
                version,
                previous_version,
                traffic_ratio,
                trigger,
                now,
                int(success),
                details,
            ),
        )
        conn.commit()
        logger.info("release_event_recorded", event_type=event_type, version=version)
        return ReleaseEvent(
            event_type=event_type,
            version=version,
            previous_version=previous_version,
            traffic_ratio=traffic_ratio,
            trigger=trigger,
            timestamp=now,
            success=success,
            details=details,
        )

    def list_releases(self, limit: int = 20) -> list[ReleaseEvent]:
        """列出最近的发布事件。"""
        rows = (
            self._get_conn()
            .execute("SELECT * FROM release_events ORDER BY id DESC LIMIT ?", (limit,))
            .fetchall()
        )
        return [
            ReleaseEvent(
                event_type=r["event_type"],
                version=r["version"],
                previous_version=r["previous_version"] or "",
                traffic_ratio=r["traffic_ratio"] or 0.0,
                trigger=r["trigger"] or "",
                timestamp=r["timestamp"],
                success=bool(r["success"]),
                details=r["details"] or "",
            )
            for r in rows
        ]

    def last_release(self) -> ReleaseEvent | None:
        """返回最近一次发布事件。"""
        row = (
            self._get_conn()
            .execute("SELECT * FROM release_events ORDER BY id DESC LIMIT 1")
            .fetchone()
        )
        if row is None:
            return None
        return ReleaseEvent(
            event_type=row["event_type"],
            version=row["version"],
            previous_version=row["previous_version"] or "",
            traffic_ratio=row["traffic_ratio"] or 0.0,
            trigger=row["trigger"] or "",
            timestamp=row["timestamp"],
            success=bool(row["success"]),
            details=row["details"] or "",
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
