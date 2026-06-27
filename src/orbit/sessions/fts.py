"""Session FTS5 全文搜索 (Phase 2 AC11).

FTS5 虚拟表管理 + BM25 查询 + snippet 高亮.
集成到 SessionRegistry 中——通过 enable_fts() 启用。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import structlog

from orbit.memory.cjk import build_fts_query
from orbit.memory.fts import (
    enable_fts,
    rank_by_bm25,
)

logger = structlog.get_logger("orbit.sessions.fts")


@dataclass
class SearchResult:
    """FTS5 搜索结果."""

    message_id: int
    session_id: str
    role: str
    snippet: str  # 高亮片段
    score: float  # BM25 分数
    created_at: float = 0.0


def setup_session_fts(conn) -> bool:
    """为 Session 数据库启用 FTS5（幂等）."""
    return enable_fts(conn)


def search_messages(
    conn,
    query: str,
    session_filter: str | None = None,
    role_filter: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """FTS5 全文搜索聊天消息——带 BM25 排序.

    Args:
        conn: sqlite3.Connection
        query: 用户搜索查询
        session_filter: 可选 session ID 过滤
        role_filter: 可选 role 过滤
        limit: 最大结果数

    Returns:
        按 BM25 分数降序排列的搜索结果
    """
    fts_query = build_fts_query(query)
    if not fts_query:
        return []

    # 构建 FTS5 MATCH 查询
    try:
        where_parts = ["chat_messages_fts MATCH ?"]
        params: list = [fts_query]

        if session_filter:
            where_parts.append("chat_messages_fts.session_id = ?")
            params.append(session_filter)
        if role_filter:
            where_parts.append("chat_messages_fts.role = ?")
            params.append(role_filter)

        sql = f"""
        SELECT
            chat_messages_fts.rowid as message_id,
            chat_messages_fts.session_id,
            chat_messages_fts.role,
            snippet(chat_messages_fts, 0, '<b>', '</b>', '...', 40) as snippet,
            cm.created_at
        FROM chat_messages_fts
        JOIN chat_messages cm ON cm.id = chat_messages_fts.rowid
        WHERE {' AND '.join(where_parts)}
        ORDER BY rank
        LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.warning("fts_search_failed", error=str(e))
        return _fallback_like_search(conn, query, session_filter, role_filter, limit)

    # BM25 重排
    if rows:
        doc_tuples = [(row[0], row[2] or "") for row in rows]
        bm25_scores = dict(rank_by_bm25(query, doc_tuples))

        results = []
        for row in rows:
            msg_id = row[0]
            score = bm25_scores.get(msg_id, 0.0)
            results.append(
                SearchResult(
                    message_id=msg_id,
                    session_id=row[1] or "",
                    role=row[2] or "",
                    snippet=row[3] or "",
                    score=score,
                    created_at=row[4] or 0.0,
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    return []


def _fallback_like_search(
    conn,
    query: str,
    session_filter: str | None = None,
    role_filter: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """FTS5 不可用时的 LIKE 回退搜索."""
    like_query = f"%{query}%"
    where_parts = ["cm.content LIKE ?"]
    params: list = [like_query]

    if session_filter:
        where_parts.append("cm.session_id = ?")
        params.append(session_filter)
    if role_filter:
        where_parts.append("cm.role = ?")
        params.append(role_filter)

    sql = f"""
    SELECT cm.id, cm.session_id, cm.role, cm.content, cm.created_at
    FROM chat_messages cm
    WHERE {' AND '.join(where_parts)}
    ORDER BY cm.created_at DESC
    LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()

    return [
        SearchResult(
            message_id=row[0],
            session_id=row[1] or "",
            role=row[2] or "",
            snippet=(row[3] or "")[:200],
            score=0.5,  # LIKE 无评分，给固定值
            created_at=row[4] or 0.0,
        )
        for row in rows
    ]
