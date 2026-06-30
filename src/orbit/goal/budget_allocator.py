"""BudgetAllocator——按子任务权重分配 Token 预算。

WHY 权重而非均分: 不同任务复杂度不同——
"写 DDL" 消耗远小于 "实现 JWT 中间件"。
权重 = 依赖数 + 关键词匹配（实现>测试>文档）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger("orbit.goal")


class BudgetAllocator:
    """按子任务权重分配 Token 预算。

    算法:
    1. 每个任务至少 min_per_task (5K tokens)
    2. 预留 15% 给 MetaOrchestrator + GoalJudge 开销
    3. 剩余预算按复杂度权重分配
    4. 权重 = 基础权重(1.0) + 依赖数(0.5/dep) + 关键词因子
    """

    def __init__(self, min_per_task: int = 5000, overhead_ratio: float = 0.15) -> None:
        self._min = min_per_task
        self._overhead = overhead_ratio

    def allocate(
        self,
        tasks: list[Any],  # list[Task]
        total_budget: int,
    ) -> dict[str, int]:
        """分配 Token 预算。

        Args:
            tasks: 子任务列表
            total_budget: 总 Token 配额

        Returns:
            {task_id: token_budget}  # 0 = 无限制
        """
        if total_budget <= 0 or not tasks:
            return {t.id: 0 for t in tasks}

        allocatable = int(total_budget * (1 - self._overhead))
        n = len(tasks)
        reserve = n * self._min

        if reserve >= allocatable:
            # 预算不够每人最低——均分
            per_task = allocatable // n if n > 0 else 0
            return {t.id: max(per_task, 1) for t in tasks}

        # 计算权重
        weights = {t.id: self._compute_weight(t) for t in tasks}
        total_weight = sum(weights.values()) or n

        remaining = allocatable - reserve
        budgets: dict[str, int] = {}
        for t in tasks:
            share = int(remaining * weights[t.id] / total_weight)
            budgets[t.id] = self._min + share

        logger.info(
            "budget_allocated",
            total=total_budget,
            allocatable=allocatable,
            task_count=n,
            budgets=budgets,
        )
        return budgets

    def _compute_weight(self, task: Any) -> float:
        """计算任务权重。

        基础 1.0 + 依赖数(0.5/dep) + 关键词因子。
        """
        weight = 1.0
        deps = getattr(task, "depends_on", [])
        weight += len(deps) * 0.5

        desc = getattr(task, "description", "").lower()
        # 实现/重构类——高权重
        if any(
            kw in desc for kw in ("实现", "implement", "重构", "refactor", "中间件", "middleware")
        ):
            weight *= 1.5
        # 测试类——中低权重
        if any(kw in desc for kw in ("测试", "test", "e2e")):
            weight *= 0.7
        # 文档/DDL/配置——低权重
        if any(kw in desc for kw in ("文档", "doc", "readme", "ddl", "迁移", "migration")):
            weight *= 0.3

        return max(weight, 0.2)
