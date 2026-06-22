"""MVP-01 调度器骨架测试。

覆盖：
- 状态转换正确性（IDLE → ... → DONE）
- 终态不可转换
- Agent 循环（mock LLM）
- 检查点保存（mock CheckpointManager）
- 异常 → FAILED
- resume 从检查点恢复
"""
from __future__ import annotations

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.orchestrator import (
    InvalidStateTransitionError,
    Scheduler,
    STATE_TRANSITIONS,
)


@pytest.fixture
def scheduler():
    # 无 LLM 无检查点（用 mock 模式）
    return Scheduler(llm_client=None, checkpoint_manager=None)


def test_state_transitions_complete():
    """所有非终态状态都有定义的后继。"""
    for state in TaskState:
        if state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
            continue
        assert state in STATE_TRANSITIONS, f"{state.value} 缺少后继定义"


def test_transition_iddle_to_done(scheduler):
    """完整路径 IDLE → DONE。"""
    state = TaskState.IDLE
    seen = [state]
    while state not in (TaskState.DONE, TaskState.FAILED):
        state = scheduler._transition(state)
        seen.append(state)
    assert seen == [
        TaskState.IDLE,
        TaskState.PARSING,
        TaskState.PLANNING,
        TaskState.CODING,
        TaskState.VERIFYING,
        TaskState.DONE,
    ]


def test_terminal_state_cannot_transition(scheduler):
    """终态转换抛异常。"""
    for terminal in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
        with pytest.raises(InvalidStateTransitionError):
            scheduler._transition(terminal)


@pytest.mark.asyncio
async def test_run_task_mock_completes(scheduler):
    """无 LLM 时用 mock 占位，跑完整流程到 DONE。"""
    final = await scheduler.run_task("task-mock", "写一个求和函数")
    assert final == TaskState.DONE


@pytest.mark.asyncio
async def test_run_task_with_llm(monkeypatch):
    """有 LLM 时每个状态调一次 generate。"""
    call_log = []

    class FakeLLM:
        async def generate(self, req, task_id):
            call_log.append(req.prompt)
            from orbit.gateway.schemas import LLMResponse, LLMUsage

            return LLMResponse(
                content=f"[{task_id}] ok",
                model="fake",
                usage=LLMUsage(),
            )

    sched = Scheduler(llm_client=FakeLLM())
    final = await sched.run_task("task-llm", "写代码")
    assert final == TaskState.DONE
    # IDLE/PARSING/PLANNING/CODING/VERIFYING 5 次 LLM 调用
    assert len(call_log) == 5


@pytest.mark.asyncio
async def test_llm_failure_marks_failed(monkeypatch):
    """LLM 异常 → 任务 FAILED。"""

    class FailingLLM:
        async def generate(self, req, task_id):
            raise Exception("LLM 不可用")

    sched = Scheduler(llm_client=FailingLLM())
    final = await sched.run_task("task-fail", "x")
    assert final == TaskState.FAILED


@pytest.mark.asyncio
async def test_checkpoint_saved_on_transition():
    """每次状态转换都保存检查点。"""
    save_log = []

    class FakeCheckpoint:
        async def save(self, task_id, data):
            save_log.append(data.state)

    sched = Scheduler(checkpoint_manager=FakeCheckpoint())
    await sched.run_task("task-ckpt", "x")
    # IDLE（初始）+ PARSING + PLANNING + CODING + VERIFYING + DONE
    assert "IDLE" in save_log
    assert "DONE" in save_log
    assert len(save_log) >= 5


@pytest.mark.asyncio
async def test_resume_from_checkpoint():
    """从检查点恢复：终端态直接返回。"""

    class FakeCheckpoint:
        def __init__(self, state, context):
            self.state = state
            self.context = context

        async def load(self, task_id):
            from orbit.checkpoint.manager import CheckpointData

            return CheckpointData(
                task_id=task_id, state=self.state, context=self.context
            )

    ckpt = FakeCheckpoint("DONE", {"prd": "x", "artifacts": {}})
    sched = Scheduler(checkpoint_manager=ckpt)
    result = await sched.resume("task-done")
    assert result == TaskState.DONE


@pytest.mark.asyncio
async def test_resume_mid_state_continues():
    """从中间状态恢复后继续执行到完成。"""

    class FakeCheckpoint:
        def __init__(self, state, context):
            self.state = state
            self.context = context

        async def load(self, task_id):
            from orbit.checkpoint.manager import CheckpointData

            return CheckpointData(
                task_id=task_id, state=self.state, context=self.context
            )

        async def save(self, task_id, data):
            pass

    ckpt = FakeCheckpoint("CODING", {"prd": "x", "artifacts": {}})
    sched = Scheduler(llm_client=None, checkpoint_manager=ckpt)
    result = await sched.resume("task-mid")
    assert result == TaskState.DONE


@pytest.mark.asyncio
async def test_resume_no_checkpoint_returns_none():
    """无检查点时 resume 返回 None。"""

    class EmptyCheckpoint:
        async def load(self, task_id):
            return None

    sched = Scheduler(checkpoint_manager=EmptyCheckpoint())
    result = await sched.resume("nonexistent")
    assert result is None


def test_state_to_progress_mapping():
    """状态映射到正确的进度值。"""
    assert Scheduler._state_to_progress(TaskState.IDLE) == 0.0
    assert Scheduler._state_to_progress(TaskState.DONE) == 1.0
    assert 0 < Scheduler._state_to_progress(TaskState.CODING) < 1.0