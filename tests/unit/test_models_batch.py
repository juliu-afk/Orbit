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
        p = TaskUpdatePayload(task_id="t1", state="coding")  # type: ignore[call-arg]
        assert p.task_id == "t1"

    def test_token_update_payload(self):
        from orbit.events.schemas import TokenUpdatePayload
        p = TokenUpdatePayload(task_id="t1", tokens_used=100)  # type: ignore[call-arg]
        assert p.tokens_used == 100


class TestGoalModels:
    def test_goal_session(self):
        from orbit.goal.models import GoalSession
        g = GoalSession(description="test goal")
        assert g.description == "test goal"


class TestMemoryModels:
    def test_memory_file_type(self):
        from orbit.memory.models import MemoryFileType
        assert len(list(MemoryFileType)) > 0


class TestSchedulerModels:
    def test_task_state(self):
        from orbit.api.schemas.task import TaskState
        states = list(TaskState)
        assert len(states) >= 6  # IDLE, PARSING, SCOPING, PLANNING, CODING, VERIFYING
