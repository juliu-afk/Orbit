"""Worktree 数据模型。

对标 OpenClaw code-agent worktree strategies。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class WorktreeStrategy(StrEnum):
    """Worktree 生命周期策略。"""

    DELEGATE = "delegate"  # Orchestrator 审查，干净→auto-merge，否则升级
    ASK = "ask"  # 显示交互按钮: Merge / PR / Later / Discard
    OFF = "off"  # 无隔离，直接在 main 工作
    MANUAL = "manual"  # Agent 自己管理分支
    AUTO_MERGE = "auto_merge"  # 成功后自动合并无需审查
    AUTO_PR = "auto_pr"  # 成功后自动开 GitHub PR


class WorktreeState(StrEnum):
    """Worktree 生命周期状态。"""

    ACTIVE = "active"
    PENDING_DECISION = "pending_decision"
    PR_OPEN = "pr_open"
    MERGED = "merged"
    RELEASED = "released"
    DISMISSED = "dismissed"
    NO_CHANGE = "no_change"


class WorktreeRecord(BaseModel):
    """Worktree 记录。"""

    worktree_id: str
    branch_name: str
    base_branch: str = "master"
    strategy: WorktreeStrategy = WorktreeStrategy.DELEGATE
    state: WorktreeState = WorktreeState.ACTIVE
    path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
