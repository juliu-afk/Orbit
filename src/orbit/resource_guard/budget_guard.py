"""单任务 Token 预算守卫 (Step 7.3 ResourceGuard).

WHY 独立于全局 TokenBucket:
- 全局桶控速率, 预算守卫控单任务上限
- 一任务超预算 ≠ 全局熔断——只阻断该任务, 不误伤其他
- 超预算 ×1.5 才触发 (PRD 熔断条件②), 给 50% 弹性空间
"""

from __future__ import annotations

from typing import Any

from orbit.resource_guard.models import BudgetRecord


class BudgetGuard:
    """单任务 Token 预算守卫。

    用法:
        guard = BudgetGuard(budget_multiplier=1.5)
        guard.set_budget("task-001", max_tokens=50000)
        guard.record_usage("task-001", 10000)
        if guard.is_over_budget("task-001"):
            ...  # 局部熔断, 只阻断此任务
    """

    def __init__(self, budget_multiplier: float = 1.5) -> None:
        self._multiplier = budget_multiplier
        self._records: dict[str, BudgetRecord] = {}

    def set_budget(self, task_id: str, max_tokens: int) -> None:
        """为任务设置 Token 预算上限。"""
        self._records[task_id] = BudgetRecord(budget=max_tokens)

    def record_usage(self, task_id: str, tokens: int) -> None:
        """记录 Token 消耗（增量）。"""
        rec = self._records.get(task_id)
        if rec is None:
            return
        rec.used += tokens
        # 超预算 × 倍数 → 标记熔断
        if not rec.tripped and rec.used > rec.budget * self._multiplier:
            rec.tripped = True

    def is_over_budget(self, task_id: str) -> bool:
        """任务是否超过预算上限。"""
        rec = self._records.get(task_id)
        if rec is None:
            return False
        return rec.tripped

    def get_usage(self, task_id: str) -> dict[str, Any]:
        """查询任务 Token 消耗情况。"""
        rec = self._records.get(task_id)
        if rec is None:
            return {"task_id": task_id, "budget": 0, "used": 0, "tripped": False}
        return {
            "task_id": task_id,
            "budget": rec.budget,
            "used": rec.used,
            "tripped": rec.tripped,
        }

    def reset(self, task_id: str) -> None:
        """重置任务预算（任务完成后释放）。"""
        self._records.pop(task_id, None)

    @property
    def active_count(self) -> int:
        return len(self._records)

    @property
    def tripped_count(self) -> int:
        return sum(1 for r in self._records.values() if r.tripped)
