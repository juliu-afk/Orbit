"""Worktree 隔离——git worktree 多工作区管理。

对标 OpenClaw code-agent worktree 6 策略:
  delegate / ask / off / manual / auto-merge / auto-pr
"""

from orbit.worktree.cleanup import WorktreeCleanup
from orbit.worktree.manager import WorktreeManager
from orbit.worktree.models import WorktreeState, WorktreeStrategy

__all__ = [
    "WorktreeCleanup",
    "WorktreeManager",
    "WorktreeState",
    "WorktreeStrategy",
]
