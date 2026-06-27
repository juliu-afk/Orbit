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
    def manager(self):
        mgr = WorktreeManager("/fake/repo")
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
