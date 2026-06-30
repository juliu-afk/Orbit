"""MVP-01 调度器骨架测试 — 适配 agent_llms 参数。

PR2 改动（2026-06-26）：Scheduler 不再接受 llm_client 参数，
改用 agent_llms dict + AgentFactory 注入。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.factory import AgentFactory
from orbit.api.schemas.task import TaskState
from orbit.scheduler.graph import GraphNode, NodeStatus, TaskGraph
from orbit.scheduler.orchestrator import (
    Scheduler,
)
from orbit.scheduler.task_runner import (
    InvalidStateTransitionError,
    STATE_TRANSITIONS,
)

# ── Mock Agent ──


class MockAgent(BaseAgent):
    def __init__(self, llm=None, graph=None, sandbox=None, role=AgentRole.DEVELOPER):
        super().__init__(llm=llm, graph=graph, sandbox=sandbox)
        self.role = role  # type: ignore[assignment]

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        key = {
            AgentRole.ARCHITECT: "design",
            AgentRole.DEVELOPER: "code",
            AgentRole.REVIEWER: "review",
            AgentRole.QA: "tests",
            AgentRole.CLARIFIER: "clarify",
        }.get(self.role, "result")
        return AgentOutput(status="ok", result={key: f"[mock {self.role.value}] ok"})


# ── Fixtures ──


@pytest.fixture
def scheduler():
    return Scheduler(agent_llms=None, checkpoint_manager=None)


@pytest.fixture
def dag_scheduler():
    return Scheduler(
        agent_llms={},
        checkpoint_manager=MagicMock(),
        max_concurrent=3,
        node_timeout=30,
        max_retries=2,
    )


@pytest.fixture
def diamond_graph():
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


# ── 状态转换 ──


def test_state_transitions_complete():
    for state in TaskState:
        if state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
            continue
        assert state in STATE_TRANSITIONS


def test_terminal_states_no_transition(scheduler):
    for state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
        with pytest.raises(InvalidStateTransitionError):
            scheduler._transition(state)


def test_state_sequence_correct(scheduler):
    seq = [
        scheduler._transition(TaskState.IDLE),
        scheduler._transition(TaskState.PARSING),
        scheduler._transition(TaskState.PLANNING),
        scheduler._transition(TaskState.CODING),
        scheduler._transition(TaskState.VERIFYING),
    ]
    assert seq == [
        TaskState.PARSING,
        TaskState.PLANNING,
        TaskState.CODING,
        TaskState.VERIFYING,
        TaskState.DONE,
    ]


# ── Phase 2: 黄金圈路由 ──


def test_golden_route_implement():
    """实现新功能 → architect + developer。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({"golden_why": "实现新功能"})
    assert route == ["architect", "developer"]


def test_golden_route_bugfix():
    """修复Bug → qa + developer + reviewer。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({"golden_why": "修复Bug"})
    assert route == ["qa", "developer", "reviewer"]


def test_golden_route_review():
    """代码审查 → reviewer。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({"golden_why": "代码审查"})
    assert route == ["reviewer"]


def test_golden_route_refactor():
    """重构 → architect + developer。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({"golden_why": "重构"})
    assert route == ["architect", "developer"]


def test_golden_route_unknown_fallback():
    """未知 Why → 默认 developer（向后兼容）。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({"golden_why": "随机任务"})
    assert route == ["developer"]


def test_golden_route_empty_context():
    """空上下文 → 默认 developer。"""
    sched = Scheduler(agent_llms={})
    route = sched._route_by_golden_why({})
    assert route == ["developer"]


# ── Agent 循环 ──


@pytest.mark.asyncio
async def test_agent_cycle_through_factory():
    AgentFactory.register(AgentRole.ARCHITECT, MockAgent)
    AgentFactory.register(AgentRole.DEVELOPER, MockAgent)
    AgentFactory.register(AgentRole.REVIEWER, MockAgent)
    AgentFactory.register(AgentRole.CLARIFIER, MockAgent)

    sched = Scheduler(agent_llms={}, agent_factory=AgentFactory)
    final = await sched.run_task("task-agent", "test")
    assert final == TaskState.DONE


@pytest.mark.asyncio
async def test_no_factory_raises():
    sched = Scheduler(agent_llms=None, agent_factory=None)
    with pytest.raises(RuntimeError, match="AgentFactory"):
        await sched._agent_cycle("t1", TaskState.CODING, {"prd": "test"})


@pytest.mark.asyncio
async def test_agent_error_handled():
    class FailingAgent(BaseAgent):
        role = AgentRole.DEVELOPER

        async def execute(self, input_data):
            raise RuntimeError("boom")

    AgentFactory.register(AgentRole.DEVELOPER, FailingAgent)
    AgentFactory.register(AgentRole.ARCHITECT, MockAgent)
    AgentFactory.register(AgentRole.REVIEWER, MockAgent)
    AgentFactory.register(AgentRole.CLARIFIER, MockAgent)

    sched = Scheduler(agent_llms={}, agent_factory=AgentFactory)
    final = await sched.run_task("task-fail", "x")
    assert final == TaskState.FAILED  # agent 异常向上传播


# ── 检查点 ──


@pytest.mark.asyncio
async def test_checkpoint_saved_on_transition():
    save_log = []

    class FakeCheckpoint:
        async def save(self, task_id, data):
            save_log.append(data.state)

    for role in [AgentRole.ARCHITECT, AgentRole.DEVELOPER, AgentRole.REVIEWER, AgentRole.CLARIFIER]:
        AgentFactory.register(role, MockAgent)

    sched = Scheduler(
        agent_llms={}, checkpoint_manager=FakeCheckpoint(), agent_factory=AgentFactory
    )
    await sched.run_task("task-ckpt", "x")
    assert "IDLE" in save_log
    assert "DONE" in save_log


@pytest.mark.asyncio
async def test_resume_from_checkpoint():
    class FakeCheckpoint:
        def __init__(self, state, context):
            self.state = state
            self.context = context

        async def load(self, task_id):
            from orbit.checkpoint.manager import CheckpointData

            return CheckpointData(task_id=task_id, state=self.state, context=self.context)

    sched = Scheduler(agent_llms=None, checkpoint_manager=FakeCheckpoint("DONE", {"prd": "x"}))
    result = await sched.resume("task-done")
    assert result == TaskState.DONE


@pytest.mark.asyncio
async def test_resume_mid_state_continues():
    class FakeCheckpoint:
        def __init__(self, state, context):
            self.state = state
            self.context = context

        async def load(self, task_id):
            from orbit.checkpoint.manager import CheckpointData

            return CheckpointData(task_id=task_id, state=self.state, context=self.context)

        async def save(self, task_id, data):
            pass

    AgentFactory.register(AgentRole.DEVELOPER, MockAgent)
    AgentFactory.register(AgentRole.REVIEWER, MockAgent)

    sched = Scheduler(
        agent_llms={},
        checkpoint_manager=FakeCheckpoint("CODING", {"prd": "x"}),
        agent_factory=AgentFactory,
    )
    result = await sched.resume("task-mid")
    assert result == TaskState.DONE


def test_state_to_progress_mapping():
    assert Scheduler._state_to_progress(TaskState.IDLE) == 0.0
    assert Scheduler._state_to_progress(TaskState.DONE) == 1.0


# ── DAG ──


@pytest.mark.asyncio
async def test_dag_topological_order(dag_scheduler, diamond_graph):
    layers = diamond_graph.topological_sort()
    assert layers[0] == ["A"]
    assert set(layers[1]) == {"B", "C"}
    assert layers[2] == ["D"]


@pytest.mark.asyncio
async def test_dag_execution_all_success(dag_scheduler, diamond_graph):
    results = await dag_scheduler.run_dag(diamond_graph)
    assert all(s == NodeStatus.SUCCESS for s in results.values())


@pytest.mark.asyncio
async def test_dag_concurrent_execution(dag_scheduler):
    graph = TaskGraph(
        task_id="concurrent",
        nodes=[GraphNode(id="A"), GraphNode(id="B"), GraphNode(id="C")],
        edges=[],
    )
    start = time.monotonic()
    await dag_scheduler.run_dag(graph)
    assert time.monotonic() - start < 0.15


@pytest.mark.asyncio
async def test_dag_resume_skips_completed(dag_scheduler, diamond_graph):
    diamond_graph.get_node("A").status = NodeStatus.SUCCESS
    diamond_graph.get_node("B").status = NodeStatus.SUCCESS
    diamond_graph.get_node("C").status = NodeStatus.SUCCESS
    results = await dag_scheduler.resume_dag(diamond_graph)
    assert results["D"] == NodeStatus.SUCCESS


@pytest.mark.asyncio
async def test_dag_node_timeout():
    sched = Scheduler(
        agent_llms={},
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=0.01,
        max_retries=0,
    )

    async def slow(n):
        await asyncio.sleep(0.1)
        return {}

    sched._execute_node = slow
    graph = TaskGraph(task_id="to", nodes=[GraphNode(id="A")], edges=[])
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED


@pytest.mark.asyncio
async def test_dag_max_retries_exceeded():
    sched = Scheduler(
        agent_llms={},
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=30,
        max_retries=2,
    )
    sched._execute_node = AsyncMock(side_effect=RuntimeError("boom"))
    graph = TaskGraph(task_id="retry", nodes=[GraphNode(id="A")], edges=[])
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED


@pytest.mark.asyncio
async def test_dag_empty_graph(dag_scheduler):
    graph = TaskGraph(task_id="empty", nodes=[], edges=[])
    results = await dag_scheduler.run_dag(graph)
    assert results == {}


@pytest.mark.asyncio
async def test_dag_fail_fast_abort():
    sched = Scheduler(
        agent_llms={},
        checkpoint_manager=MagicMock(),
        max_concurrent=1,
        node_timeout=30,
        max_retries=0,
        fail_fast=True,
    )

    async def fail_a(node):
        if node.id == "A":
            raise RuntimeError("A failed")
        return {}

    sched._execute_node = fail_a
    graph = TaskGraph(
        task_id="ff",
        nodes=[GraphNode(id="A"), GraphNode(id="B"), GraphNode(id="C")],
        edges=[("A", "B"), ("A", "C")],
    )
    results = await sched.run_dag(graph)
    assert results["A"] == NodeStatus.FAILED
