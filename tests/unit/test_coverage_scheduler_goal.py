"""覆盖率补测——scheduler/merge_engine.py + goal/models.py + goal/intake_router.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.goal.intake_router import IntakeRouter
from orbit.goal.models import (
    DependencyConflict,
    DepEdge,
    GoalBatchReport,
    GoalResult,
    GoalSession,
    IntakeDecision,
    SubTaskResult,
)
from orbit.scheduler.merge_engine import DimensionScore, MergeEngine


# ════════════════════════════════════════════
# 1. Merge Engine
# ════════════════════════════════════════════

class TestDimensionScore:
    def test_init(self):
        ds = DimensionScore(key="correctness", score=8.5, reason="good logic")
        assert ds.key == "correctness"
        assert ds.score == 8.5

    def test_default_best_of(self):
        ds = DimensionScore(key="performance", score=7.0, reason="ok")
        assert ds.best_of is None


class TestMergeEngine:
    def test_init(self):
        engine = MergeEngine(llm_client=MagicMock())
        assert engine.llm is not None

    def test_deterministic_check(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({}, "task")
        assert isinstance(scores, dict)


# ════════════════════════════════════════════
# 2. Goal models
# ════════════════════════════════════════════

class TestGoalModels:
    def test_goal_session_defaults(self):
        gs = GoalSession(description="test goal")
        assert gs.description == "test goal"
        assert gs.status == "active"

    def test_intake_decision(self):
        d = IntakeDecision(needs_clarify=True, needs_decompose=False)
        assert d.needs_clarify is True

    def test_dep_edge(self):
        e = DepEdge(from_id="goal-1", to_id="goal-2", type="explicit")
        assert e.from_id == "goal-1"

    def test_dependency_conflict(self):
        c = DependencyConflict(type="cycle", goals=["a", "b", "a"])
        assert len(c.goals) == 3

    def test_sub_task_result(self):
        r = SubTaskResult(task_id="st-1", status="ok")
        assert r.task_id == "st-1"

    def test_goal_result(self):
        r = GoalResult(status="done", tasks_completed=5)
        assert r.status == "done"

    def test_goal_batch_report(self):
        r = GoalBatchReport(total_goals=10, completed=5)
        assert r.total_goals == 10


# ════════════════════════════════════════════
# 3. IntakeRouter
# ════════════════════════════════════════════

class TestIntakeRouter:
    def test_init(self):
        router = IntakeRouter()
        assert router is not None

    @pytest.mark.asyncio
    async def test_route_returns_intake_decision(self):
        """route() 返回 IntakeDecision。"""
        router = IntakeRouter()
        goal = GoalSession(description="build a calculator")
        decision = await router.route(goal)
        assert isinstance(decision, IntakeDecision)
