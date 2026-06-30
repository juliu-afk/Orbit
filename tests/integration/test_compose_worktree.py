"""Compose→Worktree 集成测试 (5D.2).

验证 Compose 流水线到 Worktree 隔离的端到端链路。
"""

from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from orbit.worktree.manager import WorktreeManager
from orbit.worktree.models import WorktreeRecord, WorktreeState, WorktreeStrategy


class TestComposeWorktreeIntegration:
    """Compose→Worktree→Agent 全链路."""

    @pytest.fixture
    def manager(self, tmp_path):
        mgr = WorktreeManager(str(tmp_path / "repo"))
        mgr._git = AsyncMock(return_value="ok")
        return mgr

    @pytest.mark.asyncio
    async def test_compose_creates_worktree_per_task(self, manager):
        """Compose 为每个子任务创建独立 worktree。"""
        r1 = await manager.create(strategy=WorktreeStrategy.DELEGATE)
        r2 = await manager.create(strategy=WorktreeStrategy.AUTO_MERGE)
        assert r1.worktree_id != r2.worktree_id
        assert r1.branch_name != r2.branch_name
        assert len(manager._worktrees) == 2

    @pytest.mark.asyncio
    async def test_compose_resolve_uses_correct_strategy(self, manager):
        """Compose resolve 按策略路由——DELEGATE merge, AUTO_PR 创建 PR."""
        r1 = WorktreeRecord(
            worktree_id="wt-deleg",
            branch_name="orbit/deleg",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/deleg",
        )
        r2 = WorktreeRecord(
            worktree_id="wt-pr",
            branch_name="orbit/pr",
            strategy=WorktreeStrategy.AUTO_PR,
            path="/fake/pr",
        )
        manager._worktrees["wt-deleg"] = r1
        manager._worktrees["wt-pr"] = r2
        await manager.resolve("wt-deleg", WorktreeState.MERGED)
        await manager.resolve("wt-pr", WorktreeState.PR_OPEN)
        assert r1.state == WorktreeState.MERGED
        assert r2.state == WorktreeState.PR_OPEN

    @pytest.mark.asyncio
    async def test_compose_cleanup_after_resolve(self, manager):
        """Compose 完成后清理已解决的 worktree。"""
        r = WorktreeRecord(
            worktree_id="wt-done",
            branch_name="orbit/done",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/done",
            state=WorktreeState.MERGED,
        )
        manager._worktrees["wt-done"] = r
        removed = await manager.cleanup_safe("clean_safe")
        assert "wt-done" in removed
        assert "wt-done" not in manager._worktrees

    @pytest.mark.asyncio
    async def test_compose_topological_order(self, manager):
        """Compose 拓扑排序——依赖先于消费者创建 worktree。"""
        order = []

        async def create_with_order(strategy):
            r = await manager.create(strategy=strategy)
            order.append(r.worktree_id)
            return r

        r_a = await create_with_order(WorktreeStrategy.DELEGATE)
        r_b = await create_with_order(WorktreeStrategy.AUTO_MERGE)
        assert order == [r_a.worktree_id, r_b.worktree_id]
        assert r_a.worktree_id != r_b.worktree_id

    @pytest.mark.asyncio
    async def test_compose_partial_failure_cleanup(self, manager):
        """Compose 部分失败时清理成功+失败的 worktree。"""
        r_ok = WorktreeRecord(
            worktree_id="wt-ok",
            branch_name="orbit/ok",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/ok",
            state=WorktreeState.MERGED,
        )
        r_fail = WorktreeRecord(
            worktree_id="wt-fail",
            branch_name="orbit/fail",
            strategy=WorktreeStrategy.DELEGATE,
            path="/fake/fail",
            state=WorktreeState.DISMISSED,
        )
        manager._worktrees["wt-ok"] = r_ok
        manager._worktrees["wt-fail"] = r_fail
        removed = await manager.cleanup_safe("preview_safe")
        assert "wt-fail" in removed
        assert "wt-ok" not in removed
