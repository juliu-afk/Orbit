"""ProcessGuard unit tests."""
from __future__ import annotations
import pytest
from orbit.api.schemas.task import TaskState
from orbit.goal.process_guard import ProcessGuard, ProcessViolationError

class TestNormalFlow:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {}
        for s in [TaskState.IDLE, TaskState.PARSING, TaskState.PLANNING, TaskState.CODING, TaskState.VERIFYING, TaskState.DONE]:
            await guard.check(s, {"artifacts": arts})
            arts[s.value] = f"out_{s.value}"

class TestMandatoryStates:
    @pytest.mark.asyncio
    async def test_cannot_skip_parsing(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {"IDLE": "ready"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        with pytest.raises(ProcessViolationError) as exc:
            await guard.check(TaskState.PLANNING, {"artifacts": arts})
        assert "PARSING" in str(exc.value)

    @pytest.mark.asyncio
    async def test_cannot_skip_coding(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {"IDLE": "ready", "PARSING": "req", "PLANNING": "design"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        await guard.check(TaskState.PARSING, {"artifacts": arts})
        await guard.check(TaskState.PLANNING, {"artifacts": arts})
        with pytest.raises(ProcessViolationError) as exc:
            await guard.check(TaskState.VERIFYING, {"artifacts": arts})
        assert "CODING" in str(exc.value)

class TestFastLane:
    @pytest.mark.asyncio
    async def test_skips_planning(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        guard.authorize_fast_lane({"recommended_mode": "fast"})
        arts = {"IDLE": "ready", "PARSING": "req"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        await guard.check(TaskState.PARSING, {"artifacts": arts})
        await guard.check(TaskState.CODING, {"artifacts": arts})
        assert guard.fast_lane

    @pytest.mark.asyncio
    async def test_without_auth_fails(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {"IDLE": "x", "PARSING": "req"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        await guard.check(TaskState.PARSING, {"artifacts": arts})
        with pytest.raises(ProcessViolationError) as exc:
            await guard.check(TaskState.CODING, {"artifacts": arts})
        assert "PLANNING" in str(exc.value)

    def test_auth_noop_on_none(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        guard.authorize_fast_lane(None)
        assert not guard.fast_lane

class TestMissingArtifact:
    @pytest.mark.asyncio
    async def test_blocks_transition(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {"IDLE": "x"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        await guard.check(TaskState.PARSING, {"artifacts": arts})
        with pytest.raises(ProcessViolationError):
            await guard.check(TaskState.PLANNING, {"artifacts": arts})

    @pytest.mark.asyncio
    async def test_artifact_allows(self):
        guard = ProcessGuard(task_id="t1", goal_id="g1")
        arts = {"IDLE": "x", "PARSING": "req"}
        await guard.check(TaskState.IDLE, {"artifacts": arts})
        await guard.check(TaskState.PARSING, {"artifacts": arts})
        await guard.check(TaskState.PLANNING, {"artifacts": arts})
