"""Batch coverage for models/schemas across modules.
Pure Pydantic models — high statement count, zero side effects."""
from __future__ import annotations

import pytest


class TestEventSchemas:
    def test_dashboard_event(self):
        from orbit.events.schemas import DashboardEvent
        e = DashboardEvent(type="task_update", payload={"status": "running"})
        assert e.type == "task_update"

    def test_task_update_payload(self):
        from orbit.events.schemas import TaskUpdatePayload
        p = TaskUpdatePayload(task_id="t1", state="coding", progress=50)
        assert p.task_id == "t1"
        assert p.progress == 50

    def test_token_update_payload(self):
        from orbit.events.schemas import TokenUpdatePayload
        p = TokenUpdatePayload(task_id="t1", tokens_used=100, tokens_remaining=900)
        assert p.tokens_used == 100


class TestGoalModels:
    def test_goal_session(self):
        from orbit.goal.models import GoalSession
        g = GoalSession(description="test goal")
        assert g.description == "test goal"


class TestMemoryModels:
    def test_memory_file_type(self):
        from orbit.memory.models import MemoryFileType
        assert MemoryFileType.USER is not None
        assert MemoryFileType.PROJECT is not None
        assert MemoryFileType.FEEDBACK is not None

    def test_memory_file_type_values(self):
        from orbit.memory.models import MemoryFileType
        for t in MemoryFileType:
            assert isinstance(t.value, str)


class TestSchedulerModels:
    def test_task_state(self):
        from orbit.api.schemas.task import TaskState
        states = list(TaskState)
        assert len(states) >= 6  # IDLE, PARSING, SCOPING, PLANNING, CODING, VERIFYING
