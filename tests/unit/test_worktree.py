"""Worktree 模块单元测试——Manager + Models + Cleanup.

Phase 3 组 4 (AC16): 覆盖6策略、状态机、安全清理。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.worktree.manager import WorktreeManager
from orbit.worktree.models import WorktreeRecord, WorktreeState, WorktreeStrategy


class TestWorktreeModels:
    """Worktree 数据模型。"""

    def test_worktree_strategy_values(self):
        strategies = {s.value for s in WorktreeStrategy}
        expected = {"delegate", "ask", "off", "manual", "auto_merge", "auto_pr"}
        assert strategies == expected

    def test_worktree_state_values(self):
        states = {s.value for s in WorktreeState}
        expected = {
            "active",
            "pending_decision",
            "pr_open",
            "merged",
            "released",
            "dismissed",
            "no_change",
        }
        assert states == expected

    def test_worktree_record_creation(self):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-test",
            strategy=WorktreeStrategy.DELEGATE,
        )
        assert record.state == WorktreeState.ACTIVE
        assert record.base_branch == "master"


class TestWorktreeManager:
    """WorktreeManager——状态管理（mock git，测试内部逻辑）。"""

    @pytest.fixture
    def manager(self, tmp_path):
        repo = tmp_path / "repo"
        mgr = WorktreeManager(str(repo))
        # Mock _git to avoid real git calls
        mgr._git = AsyncMock(return_value="ok")
        return mgr

    @pytest.mark.asyncio
    async def test_create(self, manager):
        record = await manager.create(strategy=WorktreeStrategy.DELEGATE, base_branch="main")
        assert record.worktree_id in manager._worktrees
        assert record.branch_name.startswith("orbit/wt-")
        assert record.strategy == WorktreeStrategy.DELEGATE
        assert record.base_branch == "main"
        assert record.state == WorktreeState.ACTIVE
        manager._git.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_ensures_parent_dir(self, manager, tmp_path):
        """P1-4: create 应自动创建 .worktrees 父目录。"""
        mgr = WorktreeManager(str(tmp_path))
        mgr._git = AsyncMock(return_value="ok")
        await mgr.create()
        assert (Path(tmp_path).parent / ".worktrees").exists()

    @pytest.mark.asyncio
    async def test_resolve_delegate_merge(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-001",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/wt-001",
        )
        manager._worktrees["wt-001"] = record
        await manager.resolve("wt-001", WorktreeState.MERGED)
        assert record.state == WorktreeState.MERGED
        assert record.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_delegate_cleanup(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-002",
            branch_name="orbit/wt-002",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/wt-002",
        )
        manager._worktrees["wt-002"] = record
        await manager.resolve("wt-002", WorktreeState.DISMISSED)
        assert record.state == WorktreeState.DISMISSED

    @pytest.mark.asyncio
    async def test_resolve_auto_merge_no_change(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-003",
            branch_name="orbit/wt-003",
            strategy=WorktreeStrategy.AUTO_MERGE,
            path="/fake/wt-003",
        )
        manager._worktrees["wt-003"] = record
        await manager.resolve("wt-003", WorktreeState.NO_CHANGE)
        assert record.state == WorktreeState.NO_CHANGE

    @pytest.mark.asyncio
    async def test_resolve_auto_merge_other(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-004",
            branch_name="orbit/wt-004",
            strategy=WorktreeStrategy.AUTO_MERGE,
            path="/fake/wt-004",
        )
        manager._worktrees["wt-004"] = record
        await manager.resolve("wt-004", WorktreeState.MERGED)
        assert record.state == WorktreeState.MERGED

    @pytest.mark.asyncio
    async def test_resolve_auto_pr(self, manager):
        """P1-6: AUTO_PR 策略——state 保持 PR_OPEN，不被覆盖。"""
        record = WorktreeRecord(
            worktree_id="wt-005",
            branch_name="orbit/wt-005",
            strategy=WorktreeStrategy.AUTO_PR,
            path="/fake/wt-005",
        )
        manager._worktrees["wt-005"] = record
        await manager.resolve("wt-005", WorktreeState.MERGED)
        # _create_pr() 设置 PR_OPEN，P1-6 修复后不被覆盖
        assert record.state == WorktreeState.PR_OPEN

    @pytest.mark.asyncio
    async def test_resolve_manual_and_off(self, manager):
        """P1-6: MANUAL/OFF 策略——state 保持 ACTIVE。"""
        for strategy in (WorktreeStrategy.MANUAL, WorktreeStrategy.OFF):
            record = WorktreeRecord(
                worktree_id=f"wt-{strategy.value}",
                branch_name=f"orbit/wt-{strategy.value}",
                strategy=strategy,
                path=f"/fake/wt-{strategy.value}",
            )
            manager._worktrees[record.worktree_id] = record
            await manager.resolve(record.worktree_id, WorktreeState.RELEASED)
            # MANUAL/OFF 不覆盖 state
            assert record.state == WorktreeState.ACTIVE

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, manager):
        with pytest.raises(ValueError, match="不存在"):
            await manager.resolve("nonexistent", WorktreeState.MERGED)

    def test_list_active(self, manager):
        active = WorktreeRecord(
            worktree_id="wt-active", branch_name="orbit/a", state=WorktreeState.ACTIVE, path="/a"
        )
        merged = WorktreeRecord(
            worktree_id="wt-merged", branch_name="orbit/m", state=WorktreeState.MERGED, path="/m"
        )
        manager._worktrees["wt-active"] = active
        manager._worktrees["wt-merged"] = merged

        result = asyncio.run(manager.list_active())
        assert len(result) == 1
        assert result[0].worktree_id == "wt-active"

    def test_list_safe_to_clean_preview(self, manager):
        dismissed = WorktreeRecord(
            worktree_id="wt-d",
            branch_name="orbit/d",
            state=WorktreeState.DISMISSED,
            path="/d",
        )
        merged = WorktreeRecord(
            worktree_id="wt-m",
            branch_name="orbit/m",
            state=WorktreeState.MERGED,
            path="/m",
        )
        manager._worktrees["wt-d"] = dismissed
        manager._worktrees["wt-m"] = merged

        result = manager.list_safe_to_clean("preview_safe")
        assert result == ["wt-d"]

    def test_list_safe_to_clean_clean(self, manager):
        dismissed = WorktreeRecord(
            worktree_id="wt-d",
            branch_name="orbit/d",
            state=WorktreeState.DISMISSED,
            path="/d",
        )
        merged = WorktreeRecord(
            worktree_id="wt-m",
            branch_name="orbit/m",
            state=WorktreeState.MERGED,
            path="/m",
        )
        released = WorktreeRecord(
            worktree_id="wt-r",
            branch_name="orbit/r",
            state=WorktreeState.RELEASED,
            path="/r",
        )
        no_change = WorktreeRecord(
            worktree_id="wt-n",
            branch_name="orbit/n",
            state=WorktreeState.NO_CHANGE,
            path="/n",
        )
        manager._worktrees["wt-d"] = dismissed
        manager._worktrees["wt-m"] = merged
        manager._worktrees["wt-r"] = released
        manager._worktrees["wt-n"] = no_change

        result = manager.list_safe_to_clean("clean_safe")
        assert set(result) == {"wt-m", "wt-r", "wt-n"}

    @pytest.mark.asyncio
    async def test_cleanup_safe_preview(self, manager):
        dismissed = WorktreeRecord(
            worktree_id="wt-d",
            branch_name="orbit/d",
            state=WorktreeState.DISMISSED,
            path="/d",
        )
        active = WorktreeRecord(
            worktree_id="wt-a",
            branch_name="orbit/a",
            state=WorktreeState.ACTIVE,
            path="/a",
        )
        manager._worktrees["wt-d"] = dismissed
        manager._worktrees["wt-a"] = active

        result = await manager.cleanup_safe("preview_safe")
        assert result == ["wt-d"]
        assert "wt-d" not in manager._worktrees
        assert "wt-a" in manager._worktrees

    @pytest.mark.asyncio
    async def test_cleanup_safe_clean(self, manager):
        merged = WorktreeRecord(
            worktree_id="wt-m",
            branch_name="orbit/m",
            state=WorktreeState.MERGED,
            path="/m",
        )
        active = WorktreeRecord(
            worktree_id="wt-a",
            branch_name="orbit/a",
            state=WorktreeState.ACTIVE,
            path="/a",
        )
        manager._worktrees["wt-m"] = merged
        manager._worktrees["wt-a"] = active

        result = await manager.cleanup_safe("clean_safe")
        assert result == ["wt-m"]
        assert "wt-m" not in manager._worktrees
        assert "wt-a" in manager._worktrees

    @pytest.mark.asyncio
    async def test_merge_success(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-001",
            base_branch="main",
            path="/fake/wt-001",
        )
        await manager._merge(record)
        assert record.state != WorktreeState.DISMISSED
        # checkout + merge + branch -d = 3 calls
        assert manager._git.call_count == 3

    @pytest.mark.asyncio
    async def test_merge_conflict_rolls_back(self, manager):
        """P1-5: merge 冲突时应回滚并标记 DISMISSED。"""
        record = WorktreeRecord(
            worktree_id="wt-002",
            branch_name="orbit/wt-002",
            base_branch="main",
            path="/fake/wt-002",
        )
        # First call (checkout) succeeds, second (merge) fails
        manager._git = AsyncMock(side_effect=["ok", RuntimeError("merge conflict"), "ok"])
        await manager._merge(record)
        assert record.state == WorktreeState.DISMISSED

    @pytest.mark.asyncio
    async def test_create_pr(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-001",
            path="/fake/wt-001",
        )
        await manager._create_pr(record)
        assert record.state == WorktreeState.PR_OPEN

    @pytest.mark.asyncio
    async def test_cleanup_removes_worktree(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-001",
            path="/fake/wt-001",
        )
        with patch("orbit.worktree.manager.Path.exists", return_value=True):
            await manager._cleanup(record)
        expected_path = str(Path("/fake/wt-001"))
        manager._git.assert_called_once_with("worktree", "remove", expected_path, "--force")

    @pytest.mark.asyncio
    async def test_cleanup_skips_missing_path(self, manager):
        record = WorktreeRecord(
            worktree_id="wt-001",
            branch_name="orbit/wt-001",
            path="/nonexistent",
        )
        with patch("orbit.worktree.manager.Path.exists", return_value=False):
            await manager._cleanup(record)
        manager._git.assert_not_called()

    @pytest.mark.asyncio
    async def test_git_failure_raises(self, manager):
        """_git 应在非零返回码时抛出 RuntimeError。"""
        manager._git = AsyncMock(side_effect=RuntimeError("git command failed"))
        with pytest.raises(RuntimeError):
            await manager._git("status")


class FakeProc:
    """模拟 asyncio.create_subprocess_exec 返回值.

    WHY 独立类而非 AsyncMock: subprocess 需要 communicate()
    返回 (stdout, stderr) 元组 + returncode 属性，
    AsyncMock 无法同时满足这两个接口。
    """

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return (self._stdout, self._stderr)


class TestWorktreeManagerSubprocess:
    """_git() subprocess 层测试——FakeProc 模拟真实 git 行为.

    这类测试覆盖 _git() 实际代码路径：
    asyncio.create_subprocess_exec → communicate() → returncode 检查，
    而不只是 Mock 掉 _git() 本身。
    """

    @pytest.fixture
    def manager(self, tmp_path):
        repo = tmp_path / "repo"
        return WorktreeManager(str(repo))

    @pytest.mark.asyncio
    async def test_git_success_returns_stdout(self, manager, monkeypatch):
        """_git() 成功时应返回 stdout 字符串。"""

        async def fake_exec(*args, **kwargs):
            # args[0]="git", args[1:] 是传给 git 的子命令
            return FakeProc(returncode=0, stdout=b"branch-name\n")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        result = await manager._git("branch", "--show-current")
        # _git() 调用 stdout.decode() 保留尾部换行符
        assert result == "branch-name\n"

    @pytest.mark.asyncio
    async def test_git_nonzero_raises_runtime_error(self, manager, monkeypatch):
        """_git() 非零退出码应抛出 RuntimeError。"""

        async def fake_exec(*args, **kwargs):
            return FakeProc(returncode=128, stderr=b"fatal: not a git repository")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        with pytest.raises(RuntimeError, match="git branch"):
            await manager._git("branch")

    @pytest.mark.asyncio
    async def test_git_stderr_in_error_message(self, manager, monkeypatch):
        """_git() 失败时错误消息应包含 stderr 输出。"""

        async def fake_exec(*args, **kwargs):
            return FakeProc(returncode=1, stderr=b"error: pathspec 'xxx' did not match")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        with pytest.raises(RuntimeError, match="error: pathspec"):
            await manager._git("checkout", "xxx")

    @pytest.mark.asyncio
    async def test_git_empty_stdout(self, manager, monkeypatch):
        """_git() 正常退出但无输出时返回空字符串。"""

        async def fake_exec(*args, **kwargs):
            return FakeProc(returncode=0, stdout=b"")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        result = await manager._git("status")
        assert result == ""

    @pytest.mark.asyncio
    async def test_create_with_git_failure(self, manager, monkeypatch):
        """create() 在 git worktree add 失败时应抛出异常。"""

        async def fake_exec(*args, **kwargs):
            return FakeProc(returncode=128, stderr=b"fatal: branch already exists")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        with pytest.raises(RuntimeError, match="branch already exists"):
            await manager.create(strategy=WorktreeStrategy.DELEGATE)

    @pytest.mark.asyncio
    async def test_create_custom_base_branch(self, manager, monkeypatch):
        """create() 使用非默认 base_branch 时应传给 git worktree add。

        P2-3: 验证 git 命令参数包含 base_branch，而不仅是 record 字段。
        git 命令格式: git worktree add -b <branch> --no-track <path> <base>
        """
        called_args = []

        async def fake_exec(*args, **kwargs):
            called_args.append(args)
            return FakeProc(returncode=0, stdout=b"orbit/wt-foo\n")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        await manager.create(strategy=WorktreeStrategy.DELEGATE, base_branch="develop")

        # 验证 record
        assert manager._worktrees
        record = list(manager._worktrees.values())[0]
        assert record.base_branch == "develop"
        # 验证 git 命令——至少一次调用以 "develop" 结尾（即 git worktree add ... develop）
        assert called_args
        git_calls = [" ".join(a) for a in called_args]
        assert any("develop" in call for call in git_calls), f"未找到 base_branch 参数: {git_calls}"


class TestWorktreeManagerEdgeCases:
    """边缘情况——并发、错误恢复、不常用策略。"""

    @pytest.fixture
    def manager(self, tmp_path):
        repo = tmp_path / "repo"
        mgr = WorktreeManager(str(repo))
        mgr._git = AsyncMock(return_value="ok")
        return mgr

    @pytest.mark.asyncio
    async def test_concurrent_create_yields_unique_ids(self, manager):
        """并发 create() 应产生不同 worktree_id。"""
        import asyncio as aio

        async def _create():
            return await manager.create()

        r1, r2 = await aio.gather(_create(), _create())
        assert r1.worktree_id != r2.worktree_id
        assert r1.branch_name != r2.branch_name
        assert len(manager._worktrees) == 2

    @pytest.mark.asyncio
    async def test_resolve_ask_strategy_merged(self, manager):
        """ASK 策略 MERGED 状态——行为同 DELEGATE。"""
        record = WorktreeRecord(
            worktree_id="wt-ask",
            branch_name="orbit/wt-ask",
            strategy=WorktreeStrategy.ASK,
            path="/fake/wt-ask",
        )
        manager._worktrees["wt-ask"] = record
        await manager.resolve("wt-ask", WorktreeState.MERGED)
        assert record.state == WorktreeState.MERGED

    @pytest.mark.asyncio
    async def test_resolve_ask_strategy_dismissed(self, manager):
        """ASK 策略 DISMISSED 状态——应触发清理。"""
        record = WorktreeRecord(
            worktree_id="wt-ask2",
            branch_name="orbit/wt-ask2",
            strategy=WorktreeStrategy.ASK,
            path="/fake/wt-ask2",
        )
        manager._worktrees["wt-ask2"] = record
        await manager.resolve("wt-ask2", WorktreeState.DISMISSED)
        assert record.state == WorktreeState.DISMISSED

    @pytest.mark.asyncio
    async def test_resolve_already_resolved(self, manager):
        """resolve() 已处理记录——应保持终态。"""
        record = WorktreeRecord(
            worktree_id="wt-done",
            branch_name="orbit/wt-done",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/wt-done",
            state=WorktreeState.MERGED,
        )
        manager._worktrees["wt-done"] = record
        await manager.resolve("wt-done", WorktreeState.MERGED)
        # 已是终态，不应重复操作
        assert record.state == WorktreeState.MERGED

    @pytest.mark.asyncio
    async def test_cleanup_safe_partial_failure(self, manager):
        """cleanup_safe() 单个记录 path 不存在时静默跳过。"""
        r1 = WorktreeRecord(
            worktree_id="wt-ok",
            branch_name="orbit/wt-ok",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/wt-ok",
            state=WorktreeState.DISMISSED,
        )
        r2 = WorktreeRecord(
            worktree_id="wt-nopath",
            branch_name="orbit/wt-nopath",
            strategy=WorktreeStrategy.DELEGATE,
            path="/nonexistent",
            state=WorktreeState.DISMISSED,
        )
        manager._worktrees["wt-ok"] = r1
        manager._worktrees["wt-nopath"] = r2
        # path 不存在时 _cleanup 应跳过 git 调用，不抛异常
        with patch("orbit.worktree.manager.Path.exists", side_effect=[True, False]):
            # 只清理 preview_safe（DISMISSED 状态）
            removed = await manager.cleanup_safe("preview_safe")
        assert "wt-ok" in removed
        assert "wt-nopath" in removed  # path 不存在也删除记录（跳过 git 调用）

    @pytest.mark.asyncio
    async def test_cleanup_safe_unknown_mode_returns_empty(self, manager):
        """cleanup_safe() 使用未知 mode 应返回空列表。"""
        result = await manager.cleanup_safe("invalid_mode")
        assert result == []


class TestWorktreeCleanup:
    """WorktreeCleanup——安全清理策略。"""

    def test_cleanup_creation(self):
        from orbit.worktree.cleanup import WorktreeCleanup
        from orbit.worktree.manager import WorktreeManager

        mgr = WorktreeManager()
        cleanup = WorktreeCleanup(mgr)
        assert cleanup._manager is mgr

    @pytest.mark.asyncio
    async def test_preview_safe_delegates(self):
        from orbit.worktree.cleanup import WorktreeCleanup
        from orbit.worktree.manager import WorktreeManager

        mgr = WorktreeManager()
        mgr.list_safe_to_clean = MagicMock(return_value=["wt-1", "wt-2"])
        cleanup = WorktreeCleanup(mgr)

        result = await cleanup.preview_safe()
        assert result == ["wt-1", "wt-2"]
        mgr.list_safe_to_clean.assert_called_once_with("preview_safe")
