"""Step I1 集成胶水测试——适配 agent_llms 参数（PR2 修订）。"""

import asyncio

import pytest

from orbit.agents.base import AgentInput, AgentOutput
from orbit.agents.context import TaskContext
from orbit.scheduler.orchestrator import Scheduler


class TestBuildContext:
    """_build_context——L1-L5 上下文构建。"""

    def test_build_context_layers(self) -> None:
        sched = Scheduler()
        ctx = sched._task_runner._build_context("t1", {"prd": "测试需求", "state": "CODING"})
        assert isinstance(ctx, TaskContext)
        assert ctx.task_id == "t1"
        # L1 协作宪法
        assert "会计准则" in ctx.l1
        assert isinstance(ctx.l3, dict)
        assert ctx.l3["prd"] == "测试需求"
        assert ctx.l3["state"] == "CODING"
        assert isinstance(ctx.l4, dict)  # L4 私有记忆
        assert isinstance(ctx.l5, list)  # L5 长期记忆

    def test_build_context_defaults(self) -> None:
        sched = Scheduler()
        ctx = sched._task_runner._build_context("t2", {})
        assert ctx.l2 == {}
        # Phase 2: L4 可能从文件记忆加载内容（非严格空）
        assert isinstance(ctx.l4, dict)
        assert ctx.l5 == []


class TestRunAgent:
    """_run_agent——Agent 拉起 + 依赖注入 + 降级。

    PR1 改动：_run_agent 改调 agent.execute(AgentInput) 替代 agent.run(TaskContext)，
    依赖注入对齐 BaseAgent 实际属性（llm），不再设 message_bus/tool_registry/llm_client。
    """

    @pytest.mark.asyncio
    async def test_run_agent_no_factory_raises(self) -> None:
        """无 AgentFactory → 抛 RuntimeError（不再降级到直接 LLM）。"""
        sched = Scheduler()
        with pytest.raises(RuntimeError, match="AgentFactory"):
            await sched._task_runner._run_agent("developer", "t1", {"prd": "test"})

    @pytest.mark.asyncio
    async def test_run_agent_with_mock_factory(self) -> None:
        """有 AgentFactory → create(role, llm=) + agent.execute(AgentInput)。"""

        class MockAgent:
            role = "developer"
            llm = None

            async def execute(self, input_data: AgentInput) -> AgentOutput:
                return AgentOutput(result={"code": "mock done"})

        class MockFactory:
            @classmethod
            def create(cls, role, llm=None, **kwargs):
                agent = MockAgent()
                agent.llm = llm
                return agent

        sched = Scheduler(agent_factory=MockFactory)
        output = await sched._task_runner._run_agent("developer", "t1", {"prd": "test"})
        assert "mock done" in output

    @pytest.mark.asyncio
    async def test_run_agent_timeout(self) -> None:
        """Agent 超时 → 向上抛 TimeoutError。"""

        class SlowAgent:
            role = "developer"
            llm = None

            async def execute(self, input_data: AgentInput) -> AgentOutput:
                await asyncio.sleep(999)
                return AgentOutput()

        class SlowFactory:
            @classmethod
            def create(cls, role, llm=None, **kwargs):
                return SlowAgent()

        sched = Scheduler(agent_factory=SlowFactory)
        with pytest.raises(TimeoutError):
            await sched._task_runner._run_agent("developer", "t1", {"prd": "test"}, timeout=0.05)

    @pytest.mark.asyncio
    async def test_dependency_injection(self) -> None:
        """Agent 收到注入的 llm（对齐 BaseAgent 属性）。"""
        injected = {}

        class CheckAgent:
            role = "developer"
            llm = None

            async def execute(self, input_data: AgentInput) -> AgentOutput:
                injected["llm"] = self.llm
                return AgentOutput(result={"code": "ok"})

        class CheckFactory:
            @classmethod
            def create(cls, role, llm=None, **kwargs):
                agent = CheckAgent()
                agent.llm = llm
                return agent

        sched = Scheduler(
            agent_llms={"developer": "fake-llm"},
            agent_factory=CheckFactory,
        )
        await sched._task_runner._run_agent("developer", "t1", {"prd": "test"})
        assert injected["llm"] == "fake-llm"
