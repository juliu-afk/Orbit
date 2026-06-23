"""Step 5.3 任务分片引擎。

触發条件：PRD 字符数 > MAX_CHARS_PER_TASK（8000）。
分片策略：按段落边界（\\n\\n）切分，保证逻辑完整性。
执行：复用 Scheduler.run_task 并发执行子任务。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from orbit.scheduler.orchestrator import Scheduler

logger = structlog.get_logger()

# 单个任务最大字符数——超过此阈值触发分片
MAX_CHARS_PER_TASK = 8000
# 最大分片数——超限拒绝
MAX_SHARDS = 50


class ShardStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ShardResult:
    """单个分片执行结果。"""

    shard_id: str
    shard_index: int
    content: str
    status: ShardStatus = ShardStatus.PENDING
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class ShardPlan:
    """分片计划——父任务 + 子任务列表。"""

    parent_task_id: str
    shards: list[ShardResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.shards)

    @property
    def completed(self) -> int:
        return sum(1 for s in self.shards if s.status == ShardStatus.COMPLETED)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.shards if s.status == ShardStatus.FAILED)

    @property
    def progress(self) -> float:
        if not self.shards:
            return 0.0
        return self.completed / len(self.shards)


class TaskShardingEngine:
    """任务分片引擎。

    检测 PRD 规模 → 决定是否分片 → 按段落边界切分 → 并发执行。
    """

    def __init__(self, scheduler: Scheduler | None = None) -> None:
        self._scheduler = scheduler or Scheduler()

    def should_shard(self, prd: str) -> bool:
        """判断是否需要分片。"""
        return len(prd) > MAX_CHARS_PER_TASK

    def shard(self, prd: str, parent_task_id: str) -> ShardPlan:
        """按段落边界分片。

        WHY 段落边界而非固定字符数：保证逻辑完整性，
        不在段落中间切断。
        """
        if not self.should_shard(prd):
            # 不需要分片——单子任务
            return ShardPlan(
                parent_task_id=parent_task_id,
                shards=[
                    ShardResult(
                        shard_id=f"{parent_task_id}-s0",
                        shard_index=0,
                        content=prd,
                    )
                ],
            )

        # 按双换行（段落边界）切分
        paragraphs = prd.split("\n\n")
        shards: list[ShardResult] = []
        current = ""
        current_len = 0
        index = 0

        for para in paragraphs:
            if current_len + len(para) > MAX_CHARS_PER_TASK and current:
                # 当前累积块已满，保存并开始新块
                shards.append(
                    ShardResult(
                        shard_id=f"{parent_task_id}-s{index}",
                        shard_index=index,
                        content=current.strip(),
                    )
                )
                index += 1
                current = para
                current_len = len(para)
            else:
                if current:
                    current += "\n\n" + para
                else:
                    current = para
                current_len += len(para) + 2

            # 达到上限
            if index >= MAX_SHARDS:
                logger.warning("shard_limit_reached", max=MAX_SHARDS)
                break

        # 最后一块
        if current.strip():
            shards.append(
                ShardResult(
                    shard_id=f"{parent_task_id}-s{index}",
                    shard_index=index,
                    content=current.strip(),
                )
            )

        return ShardPlan(parent_task_id=parent_task_id, shards=shards)

    async def execute(
        self,
        prd: str,
        parent_task_id: str,
        max_concurrent: int = 3,
    ) -> ShardPlan:
        """分片 + 并发执行子任务。

        Returns:
            ShardPlan 含各分片执行结果。
        """
        plan = self.shard(prd, parent_task_id)

        if len(plan.shards) == 1:
            # 单任务——直接执行
            shard = plan.shards[0]
            shard.status = ShardStatus.RUNNING
            t0 = time.perf_counter()
            try:
                state = await self._scheduler.run_task(shard.shard_id, shard.content)
                shard.status = ShardStatus.COMPLETED
                shard.output = state.value
            except Exception as e:
                shard.status = ShardStatus.FAILED
                shard.error = str(e)
            shard.duration_ms = (time.perf_counter() - t0) * 1000
            return plan

        # 多任务——并发执行
        sem = asyncio.Semaphore(max_concurrent)

        async def run_shard(shard: ShardResult) -> None:
            async with sem:
                shard.status = ShardStatus.RUNNING
                t0 = time.perf_counter()
                try:
                    state = await self._scheduler.run_task(shard.shard_id, shard.content)
                    shard.status = ShardStatus.COMPLETED
                    shard.output = state.value
                except Exception as e:
                    shard.status = ShardStatus.FAILED
                    shard.error = str(e)
                shard.duration_ms = (time.perf_counter() - t0) * 1000

        await asyncio.gather(*[run_shard(s) for s in plan.shards])
        return plan

    def merge_results(self, plan: ShardPlan) -> str:
        """合并分片结果——按 shard_index 顺序拼接。"""
        plan.shards.sort(key=lambda s: s.shard_index)
        parts: list[str] = []
        for s in plan.shards:
            if s.status == ShardStatus.COMPLETED:
                parts.append(f"[Shard {s.shard_index}] {s.output}")
            else:
                parts.append(f"[Shard {s.shard_index} FAILED: {s.error}]")
        return "\n\n".join(parts)
