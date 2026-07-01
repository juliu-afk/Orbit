"""GoalChain——Goal 全链路构建器。

模拟 MetaOrchestrator 的完整流程：
intake→clarify（可选）→decompose→execute→critique→merge。

使用示例:
    chain = GoalChain()
    result = await chain.intake("实现多租户RBAC").decompose().execute().run()
    chain.assert_merged()
"""

from __future__ import annotations

from typing import Any

from tests.lib.builders.task_chain import TaskChain
from tests.lib.factories.agent import create_agent_output
from tests.lib.mocks.llm_client import MockLLMClient
from tests.lib.mocks.sandbox import MockSandbox
from tests.lib.mocks.checkpoint import MockCheckpointManager
from tests.lib.mocks.event_bus import MockEventBus


class GoalChain:
    """Goal 全链路构建器：intake→clarify→decompose→execute→critique→merge。"""

    def __init__(self, mocks: dict[str, Any] | None = None) -> None:
        mocks = mocks or {}
        self.llm: MockLLMClient = mocks.get("llm", MockLLMClient())
        self.sandbox: MockSandbox = mocks.get("sandbox", MockSandbox())
        self.checkpoint: MockCheckpointManager = mocks.get("checkpoint", MockCheckpointManager())
        self.event_bus: MockEventBus = mocks.get("event_bus", MockEventBus())

        # 配置
        self._goal: str = ""
        self._needs_clarify: bool = False
        self._clarify_dialogs: list[dict[str, str]] = []
        self._sub_tasks: list[str] = []
        self._pass_critique: bool = True
        self._budget_total: int = 500_000
        self._budget_spent: int = 0

        # 运行结果
        self.intake_result: dict[str, Any] = {}
        self.clarify_result: dict[str, Any] = {}
        self.sub_task_results: list[dict[str, Any]] = []
        self.critique_result: dict[str, Any] = {}
        self.merged: bool = False

    # ── 链式配置 ──────────────────────────────────────────

    def intake(self, goal_description: str) -> "GoalChain":
        """设置 Goal 描述并模拟 IntakeRouter 路由。

        Args:
            goal_description: 目标描述
        """
        self._goal = goal_description

        # 模拟 IntakeRouter.heuristic_clarity_score()
        clarity = 0.0
        if len(goal_description) < 20:
            clarity = 0.3  # 太短→需要澄清
            self._needs_clarify = True
        elif "验收标准" in goal_description or "AC" in goal_description:
            clarity = 0.9
        else:
            clarity = 0.6

        self.intake_result = {
            "goal": goal_description,
            "clarity_score": clarity,
            "needs_clarify": self._needs_clarify,
            "form": "task_only" if clarity >= 0.7 else "vague_string",
        }
        return self

    def needs_clarify(self) -> "GoalChain":
        """标记需要澄清阶段。"""
        self._needs_clarify = True
        self.intake_result["needs_clarify"] = True
        return self

    def clarify(self, dialogs: list[dict[str, str]] | None = None) -> "GoalChain":
        """执行澄清阶段—模拟 ClarifierAgent 多轮对话。

        Args:
            dialogs: 对话列表 [{"role":"user","content":"..."}, ...]
        """
        self._clarify_dialogs = dialogs or [
            {"role": "user", "content": "需要支持多租户吗？"},
            {"role": "assistant", "content": "是的，每个租户独立数据和权限"},
            {"role": "user", "content": "确认需求：多租户RBAC，5个验收标准"},
        ]
        self.clarify_result = {
            "clarified_prd": f"澄清后的需求：{self._goal}\n\n多租户隔离 + RBAC 权限控制",
            "rounds": len(self._clarify_dialogs),
            "confirmed": True,
        }
        return self

    def decompose(self, sub_tasks: list[str] | None = None) -> "GoalChain":
        """分解目标为子任务列表。

        Args:
            sub_tasks: 子任务描述列表（None→自动生成 3 个默认子任务）
        """
        self._sub_tasks = sub_tasks or [
            "实现租户 CRUD API",
            "实现角色和权限模型",
            "实现 JWT 中间件和租户隔离",
        ]
        return self

    def execute(self) -> "GoalChain":
        """执行所有子任务（通过 TaskChain）。"""
        self.sub_task_results = []
        for i, task_desc in enumerate(self._sub_tasks):
            tid = f"subtask_{i + 1}"
            result = create_agent_output(
                status="ok",
                result={
                    "output": f"[mock] {task_desc} completed",
                    "turns": 3,
                    "tool_calls": 5,
                },
            )
            self.sub_task_results.append({
                "task_id": tid,
                "description": task_desc,
                "status": "ok",
                "result": result.result,
            })
            self._budget_spent += 50_000
        return self

    def critique(self, pass_critique: bool = True) -> "GoalChain":
        """模拟 CritiqueAgent 评估。

        Args:
            pass_critique: True→审查通过，False→审查不通过需要返工
        """
        self._pass_critique = pass_critique
        self.critique_result = {
            "passed": pass_critique,
            "score": 0.85 if pass_critique else 0.4,
            "issues": [] if pass_critique else ["测试覆盖率不足", "缺少错误处理"],
        }
        return self

    # ── 执行 ──────────────────────────────────────────────

    async def run(self) -> dict[str, Any]:
        """执行完整 Goal 链路。

        Returns:
            {status, tasks_completed, total_tokens, merged, critique_passed}
        """
        if not self._goal:
            raise ValueError("must call intake() before run()")

        # Step 1: Clarify（如果 IntakeRouter 判定需要）
        if self._needs_clarify and not self._clarify_dialogs:
            self.clarify()

        # Step 2: Decompose（如果尚未手动指定子任务）
        if not self._sub_tasks:
            self.decompose()

        # Step 3: Execute
        if not self.sub_task_results:
            self.execute()

        # Step 4: Critique
        if not self.critique_result:
            self.critique()

        # Step 5: Decision
        if self._pass_critique:
            self.merged = True
            return {
                "status": "ok",
                "tasks_completed": len(self.sub_task_results),
                "total_tokens": self._budget_spent,
                "merged": True,
                "critique_passed": True,
            }
        else:
            return {
                "status": "needs_rework",
                "tasks_completed": len(self.sub_task_results),
                "total_tokens": self._budget_spent,
                "merged": False,
                "critique_passed": False,
                "issues": self.critique_result.get("issues", []),
            }

    # ── 断言 ──────────────────────────────────────────────

    def assert_merged(self) -> None:
        """断言 Goal 已成功合并。"""
        assert self.merged, "Goal 尚未合并"

    def assert_budget_not_exceeded(self) -> None:
        """断言 Token 预算未超支。"""
        assert self._budget_spent <= self._budget_total, (
            f"预算超支: spent={self._budget_spent} > total={self._budget_total}"
        )

    def assert_tasks_count(self, count: int) -> None:
        """断言子任务数量。"""
        actual = len(self.sub_task_results)
        assert actual == count, f"Expected {count} subtasks, got {actual}"

    def reset(self) -> None:
        self._goal = ""
        self._needs_clarify = False
        self._clarify_dialogs.clear()
        self._sub_tasks.clear()
        self._pass_critique = True
        self._budget_spent = 0
        self.intake_result.clear()
        self.clarify_result.clear()
        self.sub_task_results.clear()
        self.critique_result.clear()
        self.merged = False
