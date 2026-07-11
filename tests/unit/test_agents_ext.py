import pytest
class TestAgentsBase:
    def test_input(self):
        from orbit.agents.base import AgentInput
        i = AgentInput(task="test", role="developer")
        assert i.task=="test"
class TestAgentsContext:
    def test_context(self):
        from orbit.agents.context import TaskContext, ContextStage
        c = TaskContext(task_id="t1", stage=ContextStage.PREFLIGHT)
        assert c.stage==ContextStage.PREFLIGHT
class TestCheckpointMixin:
    def test_mixin(self):
        from orbit.scheduler.task_runner.checkpoint import TaskCheckpointMixin
        assert TaskCheckpointMixin is not None
class TestTaskContextMixin:
    def test_mixin(self):
        from orbit.scheduler.task_runner.context import TaskContextMixin
        assert TaskContextMixin is not None
