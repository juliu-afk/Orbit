"""PR1 ???????????

???AgentFactory.create + orchestrator._run_agent ? execute + Scheduler.run_task ????
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from orbit.agents.base import AgentInput, AgentRole
from orbit.agents.factory import AgentFactory


class TestAgentFactoryCreate:
    """AgentFactory.create ???C1/C3??"""

    def test_create_string_role(self) -> None:
        """C1/C3: ??????? create?"""
        agent = AgentFactory.create("developer")
        assert agent.role == AgentRole.DEVELOPER

    def test_create_enum_role(self) -> None:
        """????? create?"""
        agent = AgentFactory.create(AgentRole.ARCHITECT)
        assert agent.role == AgentRole.ARCHITECT

    def test_create_injects_llm(self) -> None:
        """C4: create ? llm ??? agent?"""
        agent = AgentFactory.create("developer", llm="fake_llm")  # type: ignore[arg-type]
        assert agent.llm == "fake_llm"


class TestOrchestratorRunAgent:
    """orchestrator._run_agent ? execute?C2/C5??"""

    @pytest.mark.asyncio
    async def test_run_agent_calls_execute(self) -> None:
        """C2: _run_agent ? execute ?? run?mock factory ??? execute ? agent?"""
        from orbit.agents.base import AgentOutput

        class FakeAgent:
            role = AgentRole.DEVELOPER

            async def execute(self, input_data: AgentInput) -> AgentOutput:
                return AgentOutput(result={"code": "def add(a,b): return a+b"})

        class FakeFactory:
            @classmethod
            def create(cls, role, llm=None, **kwargs):
                return FakeAgent()

        from orbit.scheduler.orchestrator import Scheduler

        sched = Scheduler(llm_client=None, agent_factory=FakeFactory)
        output = await sched._run_agent("developer", "test-task", {"prd": "???"})
        assert "add" in output or "code" in output.lower() or "ok" in output.lower()


class TestSchedulerRunTaskProgress:
    """Scheduler.run_task ????C6/C9??"""

    @pytest.mark.asyncio
    async def test_run_task_publishes_to_event_bus(self) -> None:
        """C9: run_task ???? publish ? EventBus?"""
        from orbit.events.bus import EventBus
        from orbit.scheduler.orchestrator import Scheduler

        bus = EventBus()
        sched = Scheduler(llm_client=None, event_bus=bus)

        task = asyncio.create_task(sched.run_task("test-123", "?????????????"))
        await asyncio.sleep(0.3)  # ??????

        events = []
        try:
            while True:
                ev = bus._queue.get_nowait()
                events.append(ev)
        except asyncio.QueueEmpty:
            pass

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert len(events) > 0, "EventBus ?????????"


class TestRunAgentRealFactory:
    """?? AgentFactory ???C2 ?????"""

    @pytest.mark.asyncio
    async def test_run_agent_with_real_factory_calls_execute(self) -> None:
        """_run_agent ??? AgentFactory ? execute ????? AttributeError?"""
        from orbit.agents.factory import AgentFactory
        from orbit.scheduler.orchestrator import Scheduler

        sched = Scheduler(llm_client=None, agent_factory=AgentFactory)
        output = await sched._run_agent("developer", "test-real", {"prd": "???"})
        assert "mock" in output.lower() or "code" in output.lower()

    @pytest.mark.asyncio
    async def test_scheduler_full_state_machine(self) -> None:
        """Scheduler.run_task ???????? DONE?mock llm??"""
        from orbit.agents.factory import AgentFactory
        from orbit.api.schemas.task import TaskState
        from orbit.events.bus import EventBus
        from orbit.scheduler.orchestrator import Scheduler

        bus = EventBus()
        sched = Scheduler(
            llm_client=None,
            event_bus=bus,
            agent_factory=AgentFactory,
        )
        state = await sched.run_task("test-full", "??????????")
        assert state == TaskState.DONE
