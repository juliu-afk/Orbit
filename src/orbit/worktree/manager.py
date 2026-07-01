"""WorktreeManager——git worktree 操作封装。

对标 OpenClaw code-agent 的 worktree 生命周期管理。
核心操作: create / list / remove / merge / status。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import structlog

from orbit.worktree.models import WorktreeRecord, WorktreeState, WorktreeStrategy

logger = structlog.get_logger("orbit.worktree")


class WorktreeManager:
    """Git worktree 管理器。

    Usage:
        mgr = WorktreeManager(project_root="/path/to/repo")
        record = await mgr.create(strategy=WorktreeStrategy.DELEGATE)
        # ... Agent 在 worktree 中工作 ...
        await mgr.resolve(record.worktree_id, WorktreeState.MERGED)
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self._root = Path(project_root).resolve()
        self._worktrees: dict[str, WorktreeRecord] = {}

    async def create(
        self,
        strategy: WorktreeStrategy = WorktreeStrategy.DELEGATE,
        base_branch: str = "master",
    ) -> WorktreeRecord:
        """创建新 worktree。

        Args:
            strategy: 生命周期策略
            base_branch: 基分支

        Returns:
            WorktreeRecord
        """
        worktree_id = uuid.uuid4().hex[:12]
        branch_name = f"orbit/wt-{worktree_id[:8]}"
        wt_path = self._root.parent / f".worktrees/{worktree_id}"
        # P1-4: 确保父目录存在
        wt_path.parent.mkdir(parents=True, exist_ok=True)

        record = WorktreeRecord(
            worktree_id=worktree_id,
            branch_name=branch_name,
            base_branch=base_branch,
            strategy=strategy,
            state=WorktreeState.ACTIVE,
            path=str(wt_path),
        )

        # git worktree add
        await self._git("worktree", "add", "-b", branch_name, str(wt_path), base_branch)
        self._worktrees[worktree_id] = record
        logger.info(
            "worktree_created",
            id=worktree_id,
            branch=branch_name,
            strategy=strategy.value,
        )
        return record

    async def resolve(
        self,
        worktree_id: str,
        target_state: WorktreeState,
    ) -> None:
        """解析 worktree——合并/PR/清理。"""
        record = self._worktrees.get(worktree_id)
        if record is None:
            raise ValueError(f"Worktree {worktree_id} 不存在")

        strategy = record.strategy

        if strategy == WorktreeStrategy.DELEGATE:
            if target_state == WorktreeState.MERGED:
                await self._merge(record)
            else:
                await self._cleanup(record)

        elif strategy == WorktreeStrategy.AUTO_MERGE:
            if target_state == WorktreeState.NO_CHANGE:
                await self._cleanup(record)
            else:
                await self._merge(record)

        elif strategy == WorktreeStrategy.AUTO_PR:
            await self._create_pr(record)

        elif strategy == WorktreeStrategy.MANUAL:
            pass  # Agent 自己管理

        elif strategy == WorktreeStrategy.OFF:
            pass  # 无需清理

        # P1-6: 策略分支内已设置 state 的策略不覆盖
        if strategy not in (
            WorktreeStrategy.AUTO_PR,
            WorktreeStrategy.MANUAL,
            WorktreeStrategy.OFF,
        ):
            record.state = target_state
        record.resolved_at = datetime.now(UTC)

    async def list_active(self) -> list[WorktreeRecord]:
        """列出活跃 worktree。"""
        return [r for r in self._worktrees.values() if r.state == WorktreeState.ACTIVE]

    def list_safe_to_clean(self, mode: str = "preview_safe") -> list[str]:
        """列出可安全清理的 worktree ID（只读，不执行删除）。

        P0-2: 与 cleanup_safe 分离——preview 只列表。
        """
        result = []
        for wid, record in self._worktrees.items():
            if (
                mode == "preview_safe"
                and record.state == WorktreeState.DISMISSED
                or mode == "clean_safe"
                and record.state
                in (
                    WorktreeState.MERGED,
                    WorktreeState.RELEASED,
                    WorktreeState.NO_CHANGE,
                )
            ):
                result.append(wid)
        return result

    async def cleanup_safe(self, mode: str = "preview_safe") -> list[str]:
        """安全清理 worktree。

        Args:
            mode: "preview_safe" | "clean_safe"

        Returns:
            已清理的 worktree ID 列表
        """
        cleaned = []
        for wid, record in list(self._worktrees.items()):
            if mode == "preview_safe" and record.state != WorktreeState.DISMISSED:
                continue
            if mode == "clean_safe" and record.state not in (
                WorktreeState.MERGED,
                WorktreeState.RELEASED,
                WorktreeState.NO_CHANGE,
            ):
                continue
            await self._cleanup(record)
            cleaned.append(wid)
            del self._worktrees[wid]
        return cleaned

    # ── 内部 ─────────────────────────────────────

    async def _git(self, *args: str) -> str:
        """执行 git 命令。"""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self._root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {stderr.decode()}")
        return stdout.decode()

    async def _merge(self, record: WorktreeRecord) -> None:
        """合并 worktree 分支到 base。

        P1-5: 检测 merge 冲突——冲突时回滚并标记 DISMISSED。
        """
        await self._git("checkout", record.base_branch)
        try:
            await self._git(
                "merge",
                record.branch_name,
                "--no-ff",
                "-m",
                f"merge worktree {record.worktree_id}",
            )
        except RuntimeError:
            # 合并冲突——回滚
            logger.warning("worktree_merge_conflict", id=record.worktree_id)
            with suppress(RuntimeError):
                await self._git("merge", "--abort")
            record.state = WorktreeState.DISMISSED
            return
        await self._git("branch", "-d", record.branch_name)
        logger.info("worktree_merged", id=record.worktree_id)

    async def _create_pr(self, record: WorktreeRecord) -> None:
        """创建 GitHub PR（简化——记录状态）。"""
        record.state = WorktreeState.PR_OPEN
        logger.info("worktree_pr_created", id=record.worktree_id, branch=record.branch_name)

    async def _cleanup(self, record: WorktreeRecord) -> None:
        """清理 worktree 目录和分支。"""
        wt_path = Path(record.path)
        if wt_path.exists():
            await self._git("worktree", "remove", str(wt_path), "--force")
        logger.info("worktree_cleaned", id=record.worktree_id)
