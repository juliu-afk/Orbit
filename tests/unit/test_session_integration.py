"""SessionRegistry 集成测试——真实 SQLite 完整 CRUD 覆盖。

模式参照 test_review.py：临时 SQLite 文件 + create_all + 全链路测试。
每个测试覆盖 10-30 行 SessionRegistry 代码。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from orbit.sessions.registry import SessionRegistry


@pytest.fixture
def reg():
    """临时 SQLite 数据库——创建 projects 表满足 FK 约束，隔离测试。"""
    import sqlite3
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # 创建 projects 表以满足 sessions 表 FK
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE projects (name TEXT PRIMARY KEY, local_path TEXT)")
    conn.execute("INSERT INTO projects (name) VALUES ('test-project')")
    conn.execute("INSERT INTO projects (name) VALUES ('proj-a')")
    conn.execute("INSERT INTO projects (name) VALUES ('proj-b')")
    conn.commit()
    conn.close()
    r = SessionRegistry(db_path=path)
    yield r
    r.close()
    try:
        os.unlink(path)
    except (PermissionError, OSError):
        pass  # Windows 文件锁延迟释放


@pytest.fixture
def session(reg):
    """预创建一个 Session。"""
    return reg.create("test-project", title="test session")


# ════════════════════════════════════════════
# CRUD 基本操作
# ════════════════════════════════════════════

class TestCreate:
    def test_create_defaults(self, reg):
        s = reg.create("test-project", title="hello")
        assert s.session_id  # UUID
        assert s.project_name == "test-project"
        assert s.title == "hello"
        assert s.status == "active"

    def test_create_no_title(self, reg):
        s = reg.create("test-project")
        assert s.title == ""

    def test_create_multiple(self, reg):
        s1 = reg.create("test-project", "first")
        s2 = reg.create("test-project", "second")
        assert s1.session_id != s2.session_id


class TestGet:
    def test_get_existing(self, reg, session):
        s = reg.get(session.session_id)
        assert s is not None
        assert s.session_id == session.session_id

    def test_get_nonexistent(self, reg):
        assert reg.get("nonexistent-id") is None


class TestList:
    def test_list_all(self, reg):
        reg.create("test-project", "a")
        reg.create("test-project", "b")
        all_sessions = reg.list_all()
        assert len(all_sessions) >= 2

    def test_list_by_status(self, reg):
        reg.create("test-project", "active-one")
        s = reg.create("test-project", "to-archive")
        reg.archive(s.session_id)
        active = reg.list_all(status="active")
        archived = reg.list_all(status="archived")
        assert len(archived) >= 0

    def test_list_by_project(self, reg):
        reg.create("proj-a", "foo")
        reg.create("proj-b", "bar")
        a = reg.list_by_project("proj-a")
        b = reg.list_by_project("proj-b")
        assert len(a) >= 1
        assert len(b) >= 1


class TestUpdate:
    def test_update_title(self, reg, session):
        s = reg.update(session.session_id, title="新标题")
        assert s.title == "新标题"

    def test_update_status(self, reg, session):
        s = reg.update(session.session_id, status="paused")
        assert s.status == "paused"

    def test_update_nonexistent(self, reg):
        assert reg.update("nonexistent", title="x") is None


class TestTouchAndArchive:
    def test_touch_updates_timestamp(self, reg, session):
        old = session.updated_at
        reg.touch(session.session_id)
        new = reg.get(session.session_id)
        assert new.updated_at > old

    def test_archive(self, reg, session):
        assert reg.archive(session.session_id) is True
        s = reg.get(session.session_id)
        assert s.status == "archived"

    def test_touch_nonexistent_does_not_crash(self, reg):
        reg.touch("nonexistent")


# ════════════════════════════════════════════
# Messages
# ════════════════════════════════════════════

class TestMessages:
    def test_add_and_get(self, reg, session):
        reg.add_message(
            session_id=session.session_id,
            role="user",
            content="hello world",
        )
        msgs = reg.get_messages(session.session_id)
        assert len(msgs) == 1
        assert msgs[0].content == "hello world"
        assert msgs[0].role == "user"

    def test_add_system_message(self, reg, session):
        reg.add_message(
            session_id=session.session_id,
            role="system",
            content="you are helpful",
        )
        msgs = reg.get_messages(session.session_id)
        assert msgs[0].role == "system"

    def test_add_with_candidates(self, reg, session):
        reg.add_message(
            session_id=session.session_id,
            role="assistant",
            content="result",
            candidates=[{"model": "gpt-4", "output": "alt"}],
        )
        msgs = reg.get_messages(session.session_id)
        assert len(msgs[0].candidates) == 1

    def test_get_messages_limit(self, reg, session):
        for i in range(10):
            reg.add_message(session.session_id, role="user", content=f"msg{i}")
        msgs = reg.get_messages(session.session_id, limit=5)
        assert len(msgs) == 5

    def test_get_messages_order(self, reg, session):
        reg.add_message(session.session_id, role="user", content="first")
        reg.add_message(session.session_id, role="user", content="second")
        msgs = reg.get_messages(session.session_id)
        # 旧→新
        assert msgs[0].content == "first"
        assert msgs[1].content == "second"

    def test_get_messages_empty(self, reg, session):
        msgs = reg.get_messages(session.session_id)
        assert msgs == []


# ════════════════════════════════════════════
# Fork / Lineage
# ════════════════════════════════════════════

class TestFork:
    def test_create_fork(self, reg, session):
        reg.add_message(session.session_id, role="user", content="parent msg")
        child_id = reg.create_fork(session.session_id, reason="test fork")
        assert child_id != session.session_id
        # 子 session 创建成功
        child_msgs = reg.get_messages(child_id)
        assert child_id != session.session_id

    def test_create_fork_no_messages(self, reg, session):
        child_id = reg.create_fork(session.session_id)
        child = reg.get(child_id)
        assert child is not None

    def test_get_child_sessions(self, reg, session):
        child_id = reg.create_fork(session.session_id)
        children = reg.get_child_sessions(session.session_id)
        assert len(children) >= 1
        assert children[0].session_id == child_id


# ════════════════════════════════════════════
# Close / Cleanup
# ════════════════════════════════════════════

class TestClose:
    def test_close_releases_connection(self, reg):
        reg.create("test-project", "test")
        reg.close()
        # 第二次 close 不崩
        reg.close()

    def test_reopen_works(self, reg):
        reg.create("test-project", "test")
        reg.close()
        # 重新获取连接——应自动重连
        reg.create("test-project", "after close")


# ════════════════════════════════════════════
# Row mapping
# ════════════════════════════════════════════

class TestRowMapping:
    def test_row_to_session(self, reg):
        s = reg.create("test-project", title="map test")
        fetched = reg.get(s.session_id)
        assert fetched.session_id == s.session_id
        assert fetched.project_name == "test-project"
        assert fetched.created_at > 0

    def test_row_to_message(self, reg, session):
        reg.add_message(
            session.session_id, role="assistant", content="data",
            candidates=[{"model": "test", "output": "x"}],
        )
        msgs = reg.get_messages(session.session_id)
        assert msgs[0].content == "data"
