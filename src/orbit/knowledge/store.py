"""Step 3.4a 知识存储——SQLite 后端。

WHY SQLite 而非 Neo4j：MVP 阶段零外部依赖，SQLite 足以支撑
精确查询（<50ms）。3.4c 切换 Qdrant 时接口不变。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import structlog

from orbit.knowledge.ontology.accounting import ACCOUNTING_CONCEPTS

logger = structlog.get_logger()

# DB 文件路径（项目根目录下）
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "knowledge.db"


class KnowledgeStore:
    """SQLite 知识存储。

    领域本体概念 + 来源信息 + 五级来源筛选。
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """延迟连接（按需建立）。

        WHY 在 _get_conn 内自动建表：count()/query_exact() 等方法直接查询
        knowledge_concepts 表，若表不存在会抛 "no such table"。
        在连接建立时自动建表保证所有入口安全，消除鸡生蛋问题。
        """
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._ensure_table()
        return self._conn

    def _ensure_table(self) -> None:
        """幂等建表——仅建表不插入种子数据。

        与 initialize() 分离：_ensure_table 保证查询不报错，
        initialize() 负责种子数据导入（调用方显式触发）。
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_concepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                concept TEXT NOT NULL,
                name_zh TEXT NOT NULL,
                definition TEXT NOT NULL,
                formula TEXT NOT NULL DEFAULT '',
                source_uri TEXT NOT NULL,
                source_level INTEGER NOT NULL CHECK(source_level BETWEEN 1 AND 5),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(domain, concept)
            )
        """)
        self._conn.commit()

    def initialize(self) -> None:
        """建表 + 插入种子数据。

        可重复执行——_ensure_table() + INSERT OR IGNORE 保证幂等。
        """
        conn = self._get_conn()

        # 插入种子数据（IGNORE 避免重复插入）
        for c in ACCOUNTING_CONCEPTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_concepts
                    (domain, concept, name_zh, definition, formula, source_uri, source_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    c["domain"],
                    c["concept"],
                    c["name_zh"],
                    c["definition"],
                    c.get("formula", ""),
                    c["source_uri"],
                    c["source_level"],
                ),
            )
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM knowledge_concepts").fetchone()[0]
        logger.info("knowledge_store_initialized", concepts=count)

    def query_exact(self, domain: str, concept: str) -> dict[str, Any] | None:
        """精确查询——按 domain + concept 查唯一实体。

        AC1: 零 Token，<50ms。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM knowledge_concepts WHERE domain = ? AND concept = ?",
            (domain, concept),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """按领域列出所有概念。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT concept, name_zh, definition FROM knowledge_concepts "
            "WHERE domain = ? ORDER BY source_level, concept",
            (domain,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        """概念总数。"""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM knowledge_concepts").fetchone()
        return int(row[0]) if row else 0

    def close(self, cleanup: bool = False) -> None:
        """关闭连接。

        cleanup=True 仅测试使用——删除 DB 文件。
        生产环境勿传 cleanup=True。
        """
        if self._conn:
            self._conn.close()
            self._conn = None
        if cleanup and self._db_path.exists():
            self._db_path.unlink(missing_ok=True)
