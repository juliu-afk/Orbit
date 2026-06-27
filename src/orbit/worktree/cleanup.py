"""WorktreeCleanup——安全清理策略。

对标 OpenClaw agent_worktree_cleanup(mode: "preview_safe" | "clean_safe")。
"""

from __future__ import annotations

import structlog

from orbit.worktree.manager import WorktreeManager

logger = structlog.get_logger()


class WorktreeCleanup:
    """Worktree 安全清理器。"""

    def __init__(self, manager: WorktreeManager) -> None:
        self._manager = manager

    async def preview_safe(self) -> list[str]:
        """列出可安全清理的 worktree（仅 DISMISSED 状态，不执行删除）。

        P0-2: 语义修正——preview 只列表，不删除。
        """
        return self._manager.list_safe_to_clean("preview_safe")

    async def clean_safe(self) -> list[str]:
        """安全清理已完成的 worktree（MERGED/RELEASED/NO_CHANGE）。"""
        return await self._manager.cleanup_safe("clean_safe")
