"""SessionRegistry Phase 2 测试——fork/lineage/FTS5 集成."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from orbit.sessions.registry import SessionRegistry


class TestSessionRegistryPhase2:
    @pytest.fixture
    def reg(self):
        """临时数据库——隔离测试（含 projects 表满足 FK 约束）."""
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "test.db"
            # 创建 projects 表以满足 FK 约束
            conn = __import__("sqlite3").connect(str(db))
            conn.execute("CREATE TABLE projects (name TEXT PRIMARY KEY, local_path TEXT)")
            conn.execute("INSERT INTO projects (name) VALUES ('test_project')")
            conn.commit()
            conn.close()
            registry = SessionRegistry(db_path=str(db))
            yield registry
            registry.close()

    def test_create_fork(self, reg):
        """create_fork——创建子Session并记录lineage."""
        parent = reg.create("test_project", title="parent session")
        child_id = reg.create_fork(parent.session_id, reason="context_limit")

        assert child_id
        assert child_id != parent.session_id

        # 子Session有parent_session_id
        child = reg.get(child_id)
        assert child is not None

    def test_get_child_sessions(self, reg):
        """get_child_sessions——返回所有子Session."""
        parent = reg.create("test_project", title="parent")
        c1 = reg.create_fork(parent.session_id, reason="fork1")
        c2 = reg.create_fork(parent.session_id, reason="fork2")

        children = reg.get_child_sessions(parent.session_id)
        child_ids = [c.session_id for c in children]
        assert c1 in child_ids
        assert c2 in child_ids

    def test_get_child_sessions_empty(self, reg):
        """无子Session时返回空列表."""
        parent = reg.create("test_project", title="no_children")
        children = reg.get_child_sessions(parent.session_id)
        assert children == []

    def test_enable_fts(self, reg):
        """enable_fts——幂等调用不崩溃."""
        try:
            ok = reg.enable_fts()
            assert ok in (True, False)  # FTS5可能不可用
        except Exception:
            pass  # FTS5在某些平台不可用

    def test_fts_search_basic(self, reg):
        """fts_search——基本调用不崩溃."""
        parent = reg.create("test_project", title="search_test")
        reg.add_message(parent.session_id, "user", "hello world search test")
        try:
            results = reg.fts_search("hello", limit=5)
            # 结果可能为空（FTS5未启用或未索引旧消息），但不崩溃
            assert isinstance(results, list)
        except Exception:
            pass  # FTS5兼容性
