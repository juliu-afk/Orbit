"""Goal Judge 单元测试——Verdict + fail-open + MAX_REACT + Task Gate.

Phase 3 组 2 (AC13): 覆盖目标判定、两级门禁、安全边界。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def temp_db():
    """临时 SQLite 数据库——:memory: 避免 Windows 锁问题。"""
    yield Path(":memory:")


class TestVerdictModel:
    """Verdict 模型——{ok, impossible, reason}."""

    def test_verdict_ok(self):
        from orbit.goal_judge.models import Verdict

        v = Verdict(ok=True, reason="task complete")
        assert v.ok is True
        assert v.impossible is False
        assert v.reason == "task complete"

    def test_verdict_not_ok(self):
        from orbit.goal_judge.models import Verdict

        v = Verdict(ok=False, reason="missing tests")
        assert v.ok is False

    def test_verdict_impossible(self):
        from orbit.goal_judge.models import Verdict

        v = Verdict(ok=False, impossible=True, reason="API endpoint does not exist")
        assert v.impossible is True

    def test_verdict_serializable(self):
        from orbit.goal_judge.models import Verdict

        v = Verdict(ok=True, reason="done")
        d = v.model_dump()
        assert d == {"ok": True, "impossible": False, "reason": "done"}


class TestGoalModel:
    """Goal 模型——描述 + react 计数。"""

    def test_goal_defaults(self):
        from orbit.goal_judge.models import Goal

        g = Goal(description="write unit tests")
        assert g.description == "write unit tests"
        assert g.react_count == 0
        assert g.MAX_REACT == 12

    def test_goal_max_react_custom(self):
        from orbit.goal_judge.models import Goal

        g = Goal(description="test", MAX_REACT=5)
        assert g.MAX_REACT == 5


class TestGoalJudge:
    """GoalJudge——两级门禁。"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM——返回 JSON Verdict。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value=LLMResponse(
                content='{"ok": true, "reason": "all tests pass"}',
                model="mock",
                usage=LLMUsage(),
            )
        )
        return llm

    @pytest.mark.asyncio
    async def test_task_gate_blocks_when_pending_actors(self, temp_db):
        """Task Gate——存在未完成子Actor → 阻止停止。"""
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        reg = ActorRegistry(temp_db)
        reg.register(
            ActorRecord(
                actor_id="a1",
                parent_task_id="t1",
                task="pending work",
                status=ActorStatus.PENDING,
            )
        )

        judge = GoalJudge(registry=reg)
        goal = Goal(description="finish all work")
        verdict = await judge.evaluate(goal, transcript="did some work", task_id="t1")

        assert verdict.ok is False
        assert "未完成" in verdict.reason

    @pytest.mark.asyncio
    async def test_task_gate_passes_when_no_actors(self, mock_llm):
        """无子Actor 或无 registry → task gate 通过。"""
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        judge = GoalJudge(llm=mock_llm)  # no registry
        goal = Goal(description="done")
        verdict = await judge.evaluate(goal, transcript="all done", task_id="t1")

        assert verdict.ok is True  # LLM returned ok

    @pytest.mark.asyncio
    async def test_goal_gate_llm_ok(self, mock_llm):
        """Goal Gate——LLM 判定 ok。"""
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        judge = GoalJudge(llm=mock_llm)
        goal = Goal(description="write tests")
        verdict = await judge.evaluate(goal, transcript="wrote 10 tests, all pass")

        assert verdict.ok is True
        assert goal.react_count == 1  # 消耗一次 react

    @pytest.mark.asyncio
    async def test_goal_gate_llm_not_ok(self):
        """Goal Gate——LLM 判定未完成。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value=LLMResponse(
                content='{"ok": false, "reason": "missing integration tests"}',
                model="mock",
                usage=LLMUsage(),
            )
        )

        judge = GoalJudge(llm=llm)
        goal = Goal(description="full test coverage")
        verdict = await judge.evaluate(goal, transcript="wrote unit tests only")

        assert verdict.ok is False
        assert "integration" in verdict.reason

    @pytest.mark.asyncio
    async def test_fail_open_on_parse_error(self):
        """JSON 解析失败 → fail-open（ok=true）。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        llm = AsyncMock()
        llm.generate = AsyncMock(
            return_value=LLMResponse(
                content="not valid json at all!",
                model="mock",
                usage=LLMUsage(),
            )
        )

        judge = GoalJudge(llm=llm)
        goal = Goal(description="test")
        verdict = await judge.evaluate(goal, transcript="...")

        assert verdict.ok is True  # fail-open
        assert "fail-open" in verdict.reason.lower()

    @pytest.mark.asyncio
    async def test_fail_open_on_llm_error(self):
        """LLM 异常 → fail-open。"""
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=RuntimeError("network error"))

        judge = GoalJudge(llm=llm)
        goal = Goal(description="test")
        verdict = await judge.evaluate(goal, transcript="...")

        assert verdict.ok is True  # fail-open

    @pytest.mark.asyncio
    async def test_max_react_exceeded_force_ok(self):
        """MAX_GOAL_REACT 超限 → 强制 ok。"""
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        judge = GoalJudge()  # no LLM (mock mode)
        goal = Goal(description="endless task", MAX_REACT=3)
        goal.react_count = 3  # 已达上限

        verdict = await judge.evaluate(goal, transcript="...")
        assert verdict.ok is True
        assert "MAX_GOAL_REACT" in verdict.reason

    @pytest.mark.asyncio
    async def test_mock_mode_fail_open(self):
        """无 LLM 连接 → fail-open。"""
        from orbit.goal_judge.judge import GoalJudge
        from orbit.goal_judge.models import Goal

        judge = GoalJudge(llm=None)  # mock
        goal = Goal(description="test")

        verdict = await judge.evaluate(goal, transcript="...")
        assert verdict.ok is True
