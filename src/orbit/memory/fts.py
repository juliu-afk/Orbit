"""FTS5 + BM25 全文搜索 (Phase 2 AC9/AC11).

纯 Python BM25 实现——零依赖。
FTS5 虚拟表管理 + 查询构建。
CJK bigram 分词集成。

WHY 纯 Python BM25: 避免引入搜索库依赖，代码量 <100 行。
"""

from __future__ import annotations

import math
import sqlite3

import structlog

from orbit.memory.cjk import build_fts_query

logger = structlog.get_logger("orbit.memory.fts")

# BM25 参数——对标标准实现
BM25_K1 = 1.2  # term frequency saturation
BM25_B = 0.75  # length normalization


# ── FTS5 Schema ────────────────────────────────────────

FTS5_CREATE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts
USING fts5(
    content,
    session_id UNINDEXED,
    role UNINDEXED,
    tokenize='unicode61'
);
"""

FTS5_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS chat_messages_fts_ai AFTER INSERT ON chat_messages
BEGIN
    INSERT INTO chat_messages_fts(rowid, content, session_id, role)
    VALUES (new.id, new.content, new.session_id, new.role);
END;
"""

FTS5_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS chat_messages_fts_ad AFTER DELETE ON chat_messages
BEGIN
    INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content, session_id, role)
    VALUES ('delete', old.id, old.content, old.session_id, old.role);
END;
"""

FTS5_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS chat_messages_fts_au AFTER UPDATE ON chat_messages
BEGIN
    INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content, session_id, role)
    VALUES ('delete', old.id, old.content, old.session_id, old.role);
    INSERT INTO chat_messages_fts(rowid, content, session_id, role)
    VALUES (new.id, new.content, new.session_id, new.role);
END;
"""


def enable_fts(conn: sqlite3.Connection) -> bool:
    """启用 FTS5——创建虚拟表和触发器（幂等）。

    Returns:
        True 如果 FTS5 可用并创建成功，False 如果 FTS5 未编译。
    """
    # 检测 FTS5 是否可用
    try:
        compile_options = conn.execute("PRAGMA compile_options").fetchall()
        has_fts5 = any("ENABLE_FTS5" in str(row) for row in compile_options)
        if not has_fts5:
            logger.warning("fts5_not_available", fallback="LIKE search")
            return False
    except Exception:
        pass  # 假设可用，尝试创建

    try:
        conn.executescript(FTS5_CREATE_SQL)
        conn.executescript(FTS5_TRIGGER_INSERT)
        conn.executescript(FTS5_TRIGGER_DELETE)
        conn.executescript(FTS5_TRIGGER_UPDATE)
        conn.commit()
        logger.info("fts5_enabled")
        return True
    except sqlite3.OperationalError as e:
        logger.warning("fts5_create_failed", error=str(e))
        return False


# ── BM25 Scoring ───────────────────────────────────────


def bm25_score(
    term_freq: int,
    doc_length: int,
    avg_doc_length: float,
    doc_count: int,
    doc_freq: int,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    """计算单个 term 的 BM25 分数.

    BM25 = IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))

    Args:
        term_freq: 词在文档中出现的次数
        doc_length: 文档长度（字符数）
        avg_doc_length: 平均文档长度
        doc_count: 总文档数
        doc_freq: 包含该词的文档数

    Returns:
        BM25 分数（越高越相关）
    """
    if term_freq <= 0 or doc_freq <= 0 or doc_count <= 0:
        return 0.0

    # IDF (Inverse Document Frequency)
    idf = math.log(1.0 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))

    # TF normalization
    tf_norm = (term_freq * (k1 + 1.0)) / (
        term_freq + k1 * (1.0 - b + b * doc_length / max(avg_doc_length, 1.0))
    )

    return idf * tf_norm


def rank_by_bm25(
    query: str,
    documents: list[tuple[int, str]],  # [(id, content), ...]
) -> list[tuple[int, float]]:
    """对文档列表做 BM25 排序.

    Returns:
        [(doc_id, bm25_score), ...] 按分数降序排列
    """
    if not documents or not query:
        return []

    # 分词查询
    query_tokens = build_fts_query(query).split()

    # 统计数据
    doc_count = len(documents)
    total_length = sum(len(doc[1]) for doc in documents)
    avg_doc_length = total_length / max(doc_count, 1)

    # 计算每个 token 的文档频率
    doc_freq: dict[str, int] = {}
    for _, content in documents:
        content_lower = content.lower()
        for token in set(query_tokens):
            if token.lower() in content_lower:
                doc_freq[token] = doc_freq.get(token, 0) + 1

    # 计算每个文档的 BM25 分数
    scores: list[tuple[int, float]] = []
    for doc_id, content in documents:
        score = 0.0
        content_lower = content.lower()
        doc_length = len(content)
        for token in query_tokens:
            tf = content_lower.count(token.lower())
            df = doc_freq.get(token, 0)
            score += bm25_score(tf, doc_length, avg_doc_length, doc_count, df)
        scores.append((doc_id, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
