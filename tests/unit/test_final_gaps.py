"""Final gap sweep: peak_window, loop, goal, agents."""
import pytest

class TestPeakWindow:
    def test_default_configs(self):
        from orbit.scheduler.offpeak.scheduler import DEFAULT_PEAK_CONFIGS
        assert "deepseek" in DEFAULT_PEAK_CONFIGS
        assert "anthropic" in DEFAULT_PEAK_CONFIGS
        for p, c in DEFAULT_PEAK_CONFIGS.items():
            assert "peak_windows" in c
            assert "offpeak_windows" in c

class TestLoopSchedulerExtras:
    def test_parser_init(self):
        from orbit.loop.parser import CronParser
        p = CronParser()
        assert p is not None

    def test_cron_parse_basic(self):
        from orbit.loop.parser import CronParser
        p = CronParser()
        result = p.parse("*/5 * * * *")
        assert result is not None

class TestGoalModels:
    def test_goal_types(self):
        from orbit.goal.models import GoalSession
        g = GoalSession(description="test")
        assert g.description == "test"

class TestAgentsBase:
    def test_agent_roles(self):
        from orbit.agents.base import AgentRole
        assert AgentRole.ARCHITECT.value == "architect"
        assert AgentRole.DEVELOPER.value == "developer"
        assert AgentRole.REVIEWER.value == "reviewer"

class TestObservabilitySchemas:
    def test_task_state_values(self):
        from orbit.api.schemas.task import TaskState
        states = {s.value for s in TaskState}
        assert "idle" in states
        assert "coding" in states
