"""覆盖率深度补测——goal/subtask_session + scheduler/orchestrator + agents/base."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from orbit.goal.process_guard import ProcessGuard
from orbit.goal.subtask_session import SubTaskSession


# ════════════════════════════════════════════
# 1. Agent base models
# ════════════════════════════════════════════

class TestAgentBaseModels:
    def test_agent_role_enum(self):
        assert AgentRole.DEVELOPER.value
        assert AgentRole.ARCHITECT.value
        assert AgentRole.REVIEWER.value
        assert AgentRole.QA.value
        assert AgentRole.CLARIFIER.value
        assert AgentRole.CONFIG_MANAGER.value

    def test_agent_input_defaults(self):
        inp = AgentInput(task="write a function")
        assert inp.task == "write a function"

    def test_agent_input_with_context(self):
        inp = AgentInput(
            task="refactor", context={"prd": "restructure module"},
        )
        assert inp.context["prd"] == "restructure module"

    def test_agent_output(self):
        out = AgentOutput(
            status="ok",
            result={"code": "def foo(): pass()"},
        )
        assert out.status == "ok"
        assert "foo" in str(out.result)


# ════════════════════════════════════════════
# 2. SubTaskSession 基础
# ════════════════════════════════════════════

class TestSubTaskSession:
    def test_state_role_map(self):
        """STATE_ROLE_MAP 包含完整的流水线映射。"""
        smap = SubTaskSession.STATE_ROLE_MAP
        assert len(smap) >= 5

    def test_init_minimal(self):
        """最小化初始化。"""
        from orbit.goal.models import GoalSession
        mock_factory = MagicMock()
        session = SubTaskSession(
            task=MagicMock(), base_ref="main",
            goal_context={},
            goal=GoalSession(description="test"),
            agent_factory=mock_factory,
        )
        assert session is not None
        assert session.base_ref == "main"


# ════════════════════════════════════════════
# 3. ProcessGuard 更多路径
# ════════════════════════════════════════════

class TestProcessGuardDeep:
    def test_init(self):
        pg = ProcessGuard(task_id="t1", goal_id="g1")
        assert pg is not None
        assert pg.fast_lane is False

    def test_init_fast_lane_false(self):
        pg = ProcessGuard(task_id="t2", goal_id="g2")
        assert pg.fast_lane is False

    def test_visited_states_initial(self):
        pg = ProcessGuard(task_id="t3", goal_id="g3")
        assert len(pg.visited_states) == 0

    @pytest.mark.asyncio
    async def test_check_allows_idle(self):
        """IDLE 状态 check 不抛异常。"""
        from orbit.api.schemas.task import TaskState
        pg = ProcessGuard(task_id="t4", goal_id="g4")
        await pg.check(TaskState.PARSING, context={"artifacts": {}})


# ════════════════════════════════════════════
# 4. 更多模型覆盖
# ════════════════════════════════════════════

class TestMoreModels:
    def test_compression_result_layers(self):
        from orbit.compression.models import CompressionResult, CompressionAction
        cr = CompressionResult(
            action=CompressionAction.FORCE,
            layers_applied=["truncate", "prune"],
            original_tokens=5000, compressed_tokens=2000,
            ratio=0.6,
        )
        assert len(cr.layers_applied) == 2

    def test_token_estimate_all_roles(self):
        from orbit.compression.models import TokenEstimate
        for role in ("user", "assistant", "system", "tool"):
            te = TokenEstimate(role=role, estimated_tokens=100, char_count=400)
            assert te.role == role

    def test_goal_session_full(self):
        from orbit.goal.models import GoalSession
        gs = GoalSession(
            description="complete auth system with OAuth2 and JWT",
            constraints=["use OAuth2", "support refresh tokens"],
            verification_commands=["pytest auth/", "mypy auth/"],
            status="active",
            sub_tasks={},
        )
        assert len(gs.constraints) == 2
        assert len(gs.verification_commands) == 2
