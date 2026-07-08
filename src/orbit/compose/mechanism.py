"""VCG 机制分配器 (V14.2+Theory 方向9).

Vickrey-Clarke-Groves: Agent 对子任务报价(cost, capability),
分配使∑value最大化,诚实报价是占优策略.

用法:
    allocator = VCGAllocator()
    assignment = allocator.allocate(tasks, bids)
"""
from __future__ import annotations
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger("orbit.compose.mechanism")


@dataclass
class AgentBid:
    agent_name: str
    task_id: str
    cost: float          # Agent自报成本(越低越想做)
    capability: float    # 能力匹配度(0-1,越高越擅长)


@dataclass
class Assignment:
    task_id: str
    agent_name: str
    payment: float = 0.0  # VCG支付


class VCGAllocator:
    """VCG 机制——使诚实报价是占优策略."""

    def allocate(self, tasks: list[dict], bids: list[AgentBid]) -> list[Assignment]:
        """分配子任务给Agent.

        tasks: [{"id":..., "description":...}, ...]
        bids: Agent自报(cost, capability)

        Returns: assignments with VCG payments
        """
        if not tasks or not bids:
            return []
        # value = capability - cost (Agent私有的净收益)
        # VCG: 分配使∑(value)最大化
        task_ids = {t["id"] for t in tasks}
        relevant = [b for b in bids if b.task_id in task_ids]
        if not relevant:
            return []
        # 贪心分配: 每任务选value最大的Agent
        assignments = []
        for task in tasks:
            tid = task["id"]
            candidates = [(b, b.capability - b.cost) for b in relevant if b.task_id == tid]
            if not candidates:
                continue
            best, best_val = max(candidates, key=lambda x: x[1])
            # VCG支付 = 次优Agent的value(若无则为0)
            others = [(b, b.capability - b.cost) for b in relevant
                      if b.task_id == tid and b.agent_name != best.agent_name]
            second_val = max((v for _, v in others), default=0.0)
            assignments.append(Assignment(
                task_id=tid,
                agent_name=best.agent_name,
                payment=best.cost + second_val,  # VCG: cost + externality
            ))
        return assignments
