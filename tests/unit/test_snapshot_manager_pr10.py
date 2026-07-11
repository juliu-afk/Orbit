"""PR10 回归：历史代码图谱快照——微型 git 仓库端到端。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orbit.graph.snapshot_manager import SnapshotManager


@pytest.fixture
def tiny_repo(tmp_path_factory):
    # 用与项目同盘的临时目录（Windows 跨盘 worktree 会失败）
    import os

    drive = os.path.splitdrive(os.getcwd())[0]
    base = Path(drive + os.sep) / "Temp"
    base.mkdir(exist_ok=True)
    repo = base / f"orbit_snap_test_{os.getpid()}"
    repo.mkdir(exist_ok=True)

    def _git(*a):
        subprocess.run(["git", "-C", str(repo), *a], capture_output=True, check=False)

    _git("init")
    _git("config", "user.email", "t@t.com")
    _git("config", "user.name", "T")
    (repo / "a.py").write_text("def foo():\n    return 1\n\nclass Bar:\n    def foo(self):\n        return 2\n", encoding="utf-8")
    _git("add", "a.py")
    _git("commit", "-m", "init")
    yield str(repo)
    import shutil

    shutil.rmtree(repo, ignore_errors=True)


@pytest.mark.asyncio
async def test_list_commits(tiny_repo):
    sm = SnapshotManager(tiny_repo)
    commits = await sm.list_commits(limit=10)
    assert len(commits) == 1
    assert commits[0]["message"] == "init"
    assert len(commits[0]["hash"]) == 40


@pytest.mark.asyncio
async def test_build_at_commit_isolated(tiny_repo):
    """在 commit 隔离建图——返回节点，且带缓存。含同名函数(foo)验证 find_node_by_name 不崩。"""
    sm = SnapshotManager(tiny_repo)
    commits = await sm.list_commits(limit=1)
    snap = await sm.build_at_commit(commits[0]["hash"])
    assert "nodes" in snap and "edges" in snap
    # a.py 有 foo/Bar/Bar.foo——至少几个节点，且未因同名 foo 崩溃
    assert len(snap["nodes"]) >= 1
    # 缓存命中返回同一对象
    snap2 = await sm.build_at_commit(commits[0]["hash"])
    assert snap is snap2


@pytest.mark.asyncio
async def test_list_commits_no_git(tmp_path):
    """非 git 目录返回空列表，不报错。"""
    sm = SnapshotManager(str(tmp_path))
    assert await sm.list_commits() == []
