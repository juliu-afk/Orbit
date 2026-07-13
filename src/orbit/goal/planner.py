"""Goal Mode 规划阶段 (V15.2).

将用户目标自动拆解为可验证的里程碑——规划→执行→验证闭环。
对标 Zerox Agent Goal Mode。

WHY 显式规划: LLM 说"做完了"不算数。需要:
1. 明确每个步骤的成功标准
2. 依赖关系（防止乱序执行）
3. 每步可独立验证
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import structlog

logger = structlog.get_logger("orbit.goal.planner")


@dataclass
class Milestone:
    """可验证的执行里程碑。"""

    id: str
    description: str            # 里程碑描述（人可读）
    success_criteria: str       # 可验证的成功标准（如"pytest 通过"、"文件存在"）
    depends_on: list[str] = field(default_factory=list)  # 依赖的里程碑 ID
    estimated_turns: int = 3    # 预估需要的 turns


@dataclass
class ExecutionPlan:
    """目标执行计划——里程碑的有序列表。"""

    goal_id: str
    milestones: list[Milestone]
    estimated_total_turns: int = 0

    def __post_init__(self) -> None:
        if self.estimated_total_turns == 0:
            self.estimated_total_turns = sum(
                m.estimated_turns for m in self.milestones
            )

    @property
    def next_pending(self) -> Milestone | None:
        """下一个可执行的里程碑——所有依赖已完成。"""
        for m in self.milestones:
            # 依赖的里程碑——在此简化模型中按顺序执行
            # 实际调度由 subtask_session 管理
            if all(d in self._completed_ids for d in m.depends_on):
                return m
        return self.milestones[0] if self.milestones else None

    _completed_ids: set[str] = field(default_factory=set)


# LLM 规划 prompt
PLANNING_PROMPT = """将以下目标拆解为可验证的执行步骤。每个步骤必须有明确的成功标准。

目标: {goal_description}
约束条件: {constraints}

返回格式（严格 JSON）:
{{
  "milestones": [
    {{
      "description": "步骤描述",
      "success_criteria": "可验证的成功标准（如'pytest 全部通过'、'文件 dist/index.html 存在'、'curl 返回 200'）",
      "estimated_turns": 3
    }}
  ]
}}

规则:
- 步骤数 2-7 个
- 每个成功标准必须可客观验证（文件检查/命令执行/API 调用）
- 步骤间有依赖关系的在前
- 只返回 JSON，不要其他文字"""


class GoalPlanner:
    """目标规划器——LLM 驱动的里程碑拆解。

    Usage:
        planner = GoalPlanner(llm_client)
        plan = await planner.plan(goal_description="实现用户登录功能", constraints=["REST API"])
        # plan.milestones[0].success_criteria  → "POST /login 端点返回 200 且含 JWT token"
    """

    MAX_MILESTONES = 7
    MIN_MILESTONES = 1

    def __init__(self, llm_client: object = None) -> None:
        """初始化规划器。

        Args:
            llm_client: LLM 客户端——传入 None 时使用默认线性规划（不拆里程碑）。
        """
        self._llm = llm_client

    async def plan(
        self,
        goal_description: str,
        constraints: list[str] | None = None,
    ) -> ExecutionPlan:
        """为目标生成执行计划。

        Args:
            goal_description: 目标描述
            constraints: 约束条件

        Returns:
            ExecutionPlan——含有序里程碑列表
        """
        goal_id = uuid4().hex[:12]

        if self._llm is None:
            # 默认线性规划——整个目标作为一个里程碑
            logger.info("planner_default", goal_id=goal_id)
            return self._default_plan(goal_id, goal_description)

        try:
            prompt = PLANNING_PROMPT.format(
                goal_description=goal_description[:1000],
                constraints=", ".join(constraints or ["无"]),
            )
            response = await self._llm.generate(prompt)
            plan = self._parse_response(goal_id, str(response) if response else "")
            logger.info(
                "planner_done",
                goal_id=goal_id,
                milestone_count=len(plan.milestones),
            )
            return plan

        except Exception as e:
            logger.warning("planner_failed", goal_id=goal_id, error=str(e)[:100])
            return self._default_plan(goal_id, goal_description)

    def _parse_response(self, goal_id: str, response: str) -> ExecutionPlan:
        """解析 LLM 返回的规划 JSON——失败时回退默认规划。"""
        import json as json_mod
        import re

        # 提取 JSON 块
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            raise ValueError(f"No JSON found in response: {response[:100]}")

        try:
            data = json_mod.loads(json_match.group(0))
        except json_mod.JSONDecodeError:
            raise

        milestones_raw = data.get("milestones", [])
        if not isinstance(milestones_raw, list):
            raise ValueError("milestones is not a list")

        milestones: list[Milestone] = []
        for i, m in enumerate(milestones_raw[: self.MAX_MILESTONES]):
            desc = str(m.get("description", f"步骤 {i+1}"))
            success = str(m.get("success_criteria", "任务完成"))
            turns = max(1, int(m.get("estimated_turns", 3)))
            milestones.append(
                Milestone(
                    id=f"{goal_id}-m{i+1}",
                    description=desc,
                    success_criteria=success,
                    depends_on=[f"{goal_id}-m{i}"] if i > 0 else [],
                    estimated_turns=turns,
                )
            )

        if len(milestones) < self.MIN_MILESTONES:
            raise ValueError(f"Too few milestones: {len(milestones)}")

        return ExecutionPlan(goal_id=goal_id, milestones=milestones)

    def _default_plan(self, goal_id: str, description: str) -> ExecutionPlan:
        """默认线性规划——整个目标作为单里程碑。"""
        return ExecutionPlan(
            goal_id=goal_id,
            milestones=[
                Milestone(
                    id=f"{goal_id}-m1",
                    description=description[:200],
                    success_criteria="任务完成——所有预期产出已创建",
                    estimated_turns=5,
                )
            ],
        )

    def validate_plan(self, plan: ExecutionPlan) -> bool:
        """Schema 校验——确保计划有效。

        检查:
        - 至少一个里程碑
        - 每个里程碑有非空 description 和 success_criteria
        - 无循环依赖
        """
        if not plan.milestones:
            return False

        ids = {m.id for m in plan.milestones}
        for m in plan.milestones:
            if not m.description.strip() or not m.success_criteria.strip():
                return False
            # 检查依赖是否指向已有里程碑
            for dep in m.depends_on:
                if dep not in ids:
                    return False

        # 循环依赖检测——简单 DFS
        visited: set[str] = set()
        path: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            if node_id in path:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            path.add(node_id)
            node = next((m for m in plan.milestones if m.id == node_id), None)
            if node:
                for dep in node.depends_on:
                    if has_cycle(dep):
                        return True
            path.discard(node_id)
            return False

        for m in plan.milestones:
            if has_cycle(m.id):
                return False

        return True
