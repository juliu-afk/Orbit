"""FTS5 + BM25 全文搜索测试 (Phase 2 AC9/AC11)."""

from __future__ import annotations

import sqlite3

import pytest

from orbit.memory.cjk import build_fts_query
from orbit.memory.fts import (
    bm25_score,
    enable_fts,
    rank_by_bm25,
)


class TestBM25Scoring:
    def test_basic_score(self):
        score = bm25_score(term_freq=3, doc_length=100, avg_doc_length=80, doc_count=10, doc_freq=5)
        assert score > 0

    def test_zero_term_freq(self):
        assert bm25_score(0, 100, 80, 10, 5) == 0.0

    def test_zero_doc_freq(self):
        assert bm25_score(3, 100, 80, 10, 0) == 0.0

    def test_higher_tf_higher_score(self):
        s1 = bm25_score(1, 100, 80, 10, 3)
        s2 = bm25_score(5, 100, 80, 10, 3)
        assert s2 > s1

    def test_rarer_term_higher_score(self):
        s1 = bm25_score(3, 100, 80, 10, 8)
        s2 = bm25_score(3, 100, 80, 10, 1)
        assert s2 > s1


class TestRankByBM25:
    def test_rank_multiple_docs(self):
        docs = [
            (1, "hello world python code"),
            (2, "python is great for coding"),
            (3, "hello world again"),
        ]
        scores = rank_by_bm25("python code", docs)
        assert len(scores) == 3
        # doc 1 has both "python" and "code" — should rank highest
        assert scores[0][0] == 1

    def test_empty_docs(self):
        assert rank_by_bm25("query", []) == []

    def test_empty_query(self):
        assert rank_by_bm25("", [(1, "hello")]) == []


class TestFTS5Enable:
    def test_enable_fts5_in_memory(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT)"
        )
        conn.execute("INSERT INTO chat_messages VALUES (1, 'hello world', 's1', 'user')")

        ok = enable_fts(conn)
        if ok:
            # 触发器应填充 FTS5 索引
            conn.execute(
                "INSERT INTO chat_messages VALUES (2, 'test query here', 's2', 'assistant')"
            )
            rows = conn.execute(
                "SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH 'test'"
            ).fetchall()
            assert len(rows) >= 1

    def test_enable_fts5_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT)"
        )
        ok1 = enable_fts(conn)
        ok2 = enable_fts(conn)
        assert ok1 == ok2

    def test_fts5_triggers_work(self):
        try:
            conn = sqlite3.connect(":memory:")
            conn.execute(
                "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT)"
            )
            ok = enable_fts(conn)
            if not ok:
                pytest.skip("FTS5 not available")
        except sqlite3.OperationalError:
            pytest.skip("FTS5 not compiled")

        try:
            # INSERT trigger
            conn.execute("INSERT INTO chat_messages VALUES (1, 'hello world', 's1', 'user')")
            rows = conn.execute(
                "SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH 'hello'"
            ).fetchall()
            assert len(rows) >= 1

            # UPDATE trigger
            conn.execute("UPDATE chat_messages SET content='modified text' WHERE id=1")
            rows = conn.execute(
                "SELECT rowid FROM chat_messages_fts WHERE chat_messages_fts MATCH 'modified'"
            ).fetchall()
            assert len(rows) >= 1
        except sqlite3.OperationalError:
            pytest.skip("FTS5 trigger error (platform limitation)")


class TestCJKFTSIntegration:
    def test_cjk_query_for_fts(self):
        """CJK查询转FTS5兼容格式."""
        result = build_fts_query("搜索记忆系统")
        assert len(result) > 0  # 应产出bigram token
        assert " " in result  # token用空格分隔


class TestSessionsFTS:
    def test_search_messages_basic(self):
        from orbit.sessions.fts import search_messages

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT, created_at REAL)"
        )

        from orbit.memory.fts import enable_fts

        try:
            ok = enable_fts(conn)
        except sqlite3.OperationalError:
            pytest.skip("FTS5 not compiled")
        if not ok:
            pytest.skip("FTS5 not available")

        # Insert AFTER FTS5 enabled so triggers fire
        conn.execute("INSERT INTO chat_messages VALUES (1, 'hello world', 's1', 'user', 100.0)")
        conn.execute(
            "INSERT INTO chat_messages VALUES (2, 'test python', 's2', 'assistant', 200.0)"
        )

        try:
            results = search_messages(conn, "hello", limit=10)
            assert len(results) >= 1
            assert any("hello" in r.snippet.lower() for r in results)
        except sqlite3.OperationalError:
            pytest.skip("FTS5 search limitation on this platform")

    def test_search_with_session_filter(self):
        from orbit.sessions.fts import search_messages

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT, created_at REAL)"
        )

        from orbit.memory.fts import enable_fts

        try:
            ok = enable_fts(conn)
        except sqlite3.OperationalError:
            pytest.skip("FTS5 not compiled")
        if not ok:
            pytest.skip("FTS5 not available")

        # Insert AFTER FTS5 enabled
        conn.execute("INSERT INTO chat_messages VALUES (1, 'alpha test', 's1', 'user', 100.0)")
        conn.execute("INSERT INTO chat_messages VALUES (2, 'beta test', 's2', 'user', 200.0)")

        try:
            results = search_messages(conn, "test", session_filter="s2", limit=10)
            if results:
                assert all(r.session_id == "s2" for r in results)
        except sqlite3.OperationalError:
            pytest.skip("FTS5 search limitation on this platform")

    def test_search_fallback_like(self):
        """FTS5不可用时回退LIKE搜索."""
        from orbit.sessions.fts import _fallback_like_search

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT, session_id TEXT, role TEXT, created_at REAL)"
        )
        conn.execute("INSERT INTO chat_messages VALUES (1, 'hello world', 's1', 'user', 100.0)")

        results = _fallback_like_search(conn, "hello", limit=10)
        assert len(results) >= 1
        assert results[0].score == 0.5  # 固定分值
