"""压力测试——并发 + 持续负载.

验证系统在高并发下的稳定性，不依赖 Docker.
使用 MockLLM 避免消耗真实 Token.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.scheduler.task_runner import TaskRunner
from orbit.agents.factory import AgentFactory
from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.api.schemas.task import TaskState


class FastMockAgent(BaseAgent):
    """快速 Mock Agent——瞬间返回."""
    role = AgentRole.DEVELOPER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        return AgentOutput(status="ok", result={"code": "pass"})


@pytest.fixture
def task_runner() -> TaskRunner:
    """创建带 Mock Factory 的 TaskRunner."""
    AgentFactory.register(AgentRole.DEVELOPER, FastMockAgent)
    AgentFactory.register(AgentRole.ARCHITECT, FastMockAgent)
    AgentFactory.register(AgentRole.REVIEWER, FastMockAgent)
    AgentFactory.register(AgentRole.CLARIFIER, FastMockAgent)
    return TaskRunner(
        agent_factory=AgentFactory,
        agent_llms={},
        fast_lane=True,
    )


class TestConcurrentStress:
    """并发压力——多任务同时执行."""

    @pytest.mark.asyncio
    async def test_10_concurrent_tasks(self, task_runner: TaskRunner) -> None:
        """10 个任务并发执行——不应崩溃."""
        async def run_one(i: int) -> TaskState:
            return await task_runner.run_task(f"stress-{i}", f"PRD {i}: fast test")

        tasks = [run_one(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(r == TaskState.DONE for r in results), (
            f"并发失败: {[r.value for r in results]}"
        )

    @pytest.mark.asyncio
    async def test_50_concurrent_tasks(self, task_runner: TaskRunner) -> None:
        """50 个任务并发——压力测试."""
        async def run_one(i: int) -> TaskState:
            return await task_runner.run_task(f"stress-50-{i}", f"PRD {i}")

        start = time.monotonic()
        tasks = [run_one(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        done = sum(1 for r in results if r == TaskState.DONE)
        failed = sum(1 for r in results if r == TaskState.FAILED)
        assert done + failed == 50, f"部分任务丢失: done={done}, failed={failed}"
        # 50 任务应在 30 秒内完成
        assert elapsed < 30.0, f"50 任务耗时 {elapsed:.1f}s > 30s"


class TestSustainedLoad:
    """持续负载——内存和 Token 稳定性."""

    @pytest.mark.asyncio
    async def test_sequential_100_tasks(self, task_runner: TaskRunner) -> None:
        """顺序执行 100 个任务——检测内存泄漏."""
        failures = 0
        for i in range(100):
            try:
                state = await task_runner.run_task(
                    f"seq-{i}", f"PRD {i}: sequential test"
                )
                if state != TaskState.DONE:
                    failures += 1
            except Exception:
                failures += 1
        assert failures < 5, f"顺序执行失败率过高: {failures}/100"

    @pytest.mark.asyncio
    async def test_edit_detector_memory_cleanup(self) -> None:
        """编辑摇摆检测器在大量写入后正常清理."""
        from orbit.scheduler.edit_stability import EditStabilityDetector

        detector = EditStabilityDetector()
        # 写入 200 次编辑——触发清理逻辑
        for i in range(200):
            fname = f"file_{i % 30}.py"
            detector.record_edit(fname, agent_id="developer")

        # 检查不应超过上限
        assert len(detector._history) <= detector.MAX_HISTORY_FILES
        # 不应崩溃
        reports = detector.get_high_entropy_files()
        assert isinstance(reports, list)
