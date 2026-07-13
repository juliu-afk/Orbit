"""搜索结果缓存 (V15.2).

SQLite TTL 缓存——相同查询在 TTL 内直接返回缓存结果，
减少外部 API 调用和延迟。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger("orbit.knowledge.search.cache")


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    total_entries: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class SearchCache:
    """SQLite TTL 搜索结果缓存。

    WHY SQLite: 零新依赖，复用现有基础设施，支持并发读。

    Usage:
        cache = SearchCache(":memory:")
        cached = cache.get("query_hash")
        if cached is None:
            results = await do_search()
            cache.set("query_hash", results)
    """

    DEFAULT_TTL = 1800  # 30 分钟

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS search_cache (
        query_hash TEXT PRIMARY KEY,
        query_text TEXT NOT NULL,
        results_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        ttl INTEGER NOT NULL DEFAULT 1800
    );
    CREATE INDEX IF NOT EXISTS idx_sc_created ON search_cache(created_at);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()
        self._stats = CacheStats()

    def _hash(self, query: str) -> str:
        """规范化查询后取 hash——忽略大小写和多余空格。"""
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    def get(self, query: str) -> list[dict] | None:
        """查询缓存——TTL 未过期返回结果，过期或不存在返回 None。"""
        h = self._hash(query)
        row = self._db.execute(
            "SELECT results_json, created_at, ttl FROM search_cache WHERE query_hash = ?",
            (h,),
        ).fetchone()

        if row is None:
            self._stats.misses += 1
            return None

        if time.time() - row["created_at"] > row["ttl"]:
            self._db.execute("DELETE FROM search_cache WHERE query_hash = ?", (h,))
            self._db.commit()
            self._stats.misses += 1
            logger.debug("cache_expired", query_hash=h[:8])
            return None

        self._stats.hits += 1
        logger.debug("cache_hit", query_hash=h[:8])
        return json.loads(row["results_json"])

    def set(
        self, query: str, results: list[dict], ttl: int = DEFAULT_TTL
    ) -> None:
        """写入缓存——覆盖同 query 的旧条目。"""
        h = self._hash(query)
        self._db.execute(
            """INSERT OR REPLACE INTO search_cache
               (query_hash, query_text, results_json, created_at, ttl)
               VALUES (?, ?, ?, ?, ?)""",
            (h, query, json.dumps(results, ensure_ascii=False), time.time(), ttl),
        )
        self._db.commit()
        self._stats.total_entries = self._count()
        logger.debug("cache_set", query_hash=h[:8], result_count=len(results))

    def clear_expired(self) -> int:
        """清理过期缓存条目——返回清理数。"""
        c = self._db.execute(
            "DELETE FROM search_cache WHERE created_at + ttl < ?",
            (time.time(),),
        )
        self._db.commit()
        if c.rowcount:
            logger.info("cache_cleared", count=c.rowcount)
        return c.rowcount

    def hit_rate(self) -> float:
        return self._stats.hit_rate

    def _count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM search_cache").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._db.close()
