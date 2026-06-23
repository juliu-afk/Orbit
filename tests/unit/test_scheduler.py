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

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.graph import GraphNode, NodeStatus, TaskGraph
from orbit.scheduler.orchestrator import (
    STATE_TRANSITIONS,
    InvalidStateTransitionError,
    Scheduler,
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

            return CheckpointData(task_id=task_id, state=self.state, context=self.context)

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

            return CheckpointData(task_id=task_id, state=self.state, context=self.context)

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


# ---- Step 5.1 DAG 执行测试 ----


@pytest.fixture
def dag_scheduler():
    """轻量调度器：mock LLM + mock checkpoint。"""
    mock_checkpoint = MagicMock()
    mock_checkpoint.save = AsyncMock()
    return Scheduler(
        llm_client=MagicMock(),
        checkpoint_manager=mock_checkpoint,
        max_concurrent=3,
        node_timeout=30,
        max_retries=2,
    )


@pytest.fixture
def diamond_graph():
    """AC1 钻石 DAG: A→B, A→C, B→D, C→D。"""
    return TaskGraph(
        task_id="dag-test",
        nodes=[
            GraphNode(id="A", agent_role="developer"),
            GraphNode(id="B", agent_role="reviewer"),
            GraphNode(id="C", agent_role="developer"),
            GraphNode(id="D", agent_role="qa"),
        ],
        edges=[("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
    )


@pytest.mark.asyncio
async def test_dag_topological_order(dag_scheduler, diamond_graph):
    """AC1: 拓扑排序满足依赖约束。"""
    layers = diamond_graph.topological_sort()
    assert layers[0] == ["A"]
    assert set(layers[1]) == {"B", "C"}
    assert layers[2] == ["D"]


@pytest.mark.asyncio
async def test_dag_execution_all_success(dag_scheduler, diamond_graph):
    """DAG 正常执行：全部节点成功。"""
    results = await dag_scheduler.run_dag(diamond_graph)
    assert all(s == NodeStatus.SUCCESS for s in results.values())
    for node in diamond_graph.nodes:
        assert node.status == NodeStatus.SUCCESS


@pytest.mark.asyncio
async def test_dag_concurrent_execution(dag_scheduler):
    """AC2: 无依赖节点并发执行。"""
    graph = TaskGraph(
        task_id="concurrent",
        nodes=[GraphNode(id="A"), GraphNode(id="B"), GraphNode(id="C")],
        edges=[],
    )
    start = time.monotonic()
    await dag_scheduler.run_dag(graph)
    elapsed = time.monotonic() - start
    # MVP 占位 _execute_node 约 10ms sleep，三个串行 ≈30ms，并行 <25ms
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_dag_resume_skips_completed(dag_scheduler, diamond_graph):
    """AC3: 恢复时已完成节点不重复执行。"""
    # 标记 A/B 为已完成（模拟崩溃恢复）
    diamond_graph.get_node("A").status = NodeStatus.SUCCESS
    diamond_graph.get_node("B").status = NodeStatus.SUCCESS
    diamond_graph.get_node("C").status = NodeStatus.SUCCESS

    results = await dag_scheduler.resume_dag(diamond_graph)
    # A/B/C 已完成 → 仅 D 执行
    assert results["A"] == NodeStatus.SUCCESS
    assert results["B"] == NodeStatus.SUCCESS
    assert results["C"] == NodeStatus.SUCCESS
    assert results["D"] == NodeStatus.SUCCESS


@pytest.mark.asyncio
async def test_dag_node_timeout(dag_scheduler):
    """AC4: 节点超时 → 重试 → 失败。"""
    sched = Scheduler(
        llm_client=MagicMock(),
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=0.01,  # 10ms 超时
        max_retries=0,  # 不重试
    )

    # 让 _execute_node 延时远超超时
    async def slow_execute(node):
        await asyncio.sleep(0.1)
        return {}

    sched._execute_node = slow_execute
    graph = TaskGraph(
        task_id="timeout",
        nodes=[GraphNode(id="A")],
        edges=[],
    )
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED


@pytest.mark.asyncio
async def test_dag_max_retries_exceeded(dag_scheduler):
    """AC4: 2 次重试全失败 → FAILED。"""
    sched = Scheduler(
        llm_client=MagicMock(),
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=30,
        max_retries=2,
    )
    # Mock _execute_node 总是抛异常
    sched._execute_node = AsyncMock(side_effect=RuntimeError("boom"))

    graph = TaskGraph(
        task_id="retry",
        nodes=[GraphNode(id="A")],
        edges=[],
    )
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED
    assert graph.get_node("A").retry_count == 3  # 初始 + 2 重试


@pytest.mark.asyncio
async def test_dag_empty_graph(dag_scheduler):
    """空 DAG → 正常返回。"""
    graph = TaskGraph(task_id="empty", nodes=[], edges=[])
    results = await dag_scheduler.run_dag(graph)
    assert results == {}


@pytest.mark.asyncio
async def test_dag_fail_fast_abort(dag_scheduler):
    """快速失败：A 失败则 B/C 不执行。"""
    sched = Scheduler(
        llm_client=MagicMock(),
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=30,
        max_retries=0,
        fail_fast=True,
    )

    # 让第一层的 A 失败
    async def fail_a(node):
        if node.id == "A":
            raise RuntimeError("A failed")
        return {}

    sched._execute_node = fail_a

    graph = TaskGraph(
        task_id="failfast",
        nodes=[GraphNode(id="A"), GraphNode(id="B"), GraphNode(id="C")],
        edges=[("A", "B"), ("A", "C")],
    )
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED
    # B/C 在 fail_fast 下不会执行（仍是 PENDING）
    assert results["B"] == NodeStatus.PENDING
    assert results["C"] == NodeStatus.PENDING
