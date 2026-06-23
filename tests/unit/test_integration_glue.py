"""Step I1——集成胶水单元测试。"""

import pytest

from orbit.agents.context import TaskContext
from orbit.scheduler.orchestrator import Scheduler


class TestBuildContext:
    """_build_context——L1-L5 上下文构建。"""

    def test_build_context_layers(self) -> None:
        sched = Scheduler()
        ctx = sched._build_context("t1", {"prd": "测试需求", "state": "CODING"})
        assert isinstance(ctx, TaskContext)
        assert ctx.task_id == "t1"
        assert "小企业会计准则" in ctx.l1  # L1 协作宪法
        assert isinstance(ctx.l3, dict)
        assert ctx.l3["prd"] == "测试需求"
        assert ctx.l3["state"] == "CODING"
        assert isinstance(ctx.l4, dict)  # L4 私有记忆
        assert isinstance(ctx.l5, list)  # L5 长期记忆

    def test_build_context_defaults(self) -> None:
        sched = Scheduler()
        ctx = sched._build_context("t2", {})
        assert ctx.l2 == {}
        assert ctx.l4 == {}
        assert ctx.l5 == []


class TestRunAgent:
    """_run_agent——Agent 拉起 + 依赖注入 + 降级。"""

    @pytest.mark.asyncio
    async def test_run_agent_fallback_to_llm(self) -> None:
        """无 AgentFactory → 降级为直接 LLM 调用。"""
        sched = Scheduler()
        output = await sched._run_agent("developer", "t1", {"prd": "test"})
        assert isinstance(output, str)
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_run_agent_with_mock_factory(self) -> None:
        """有 AgentFactory → 创建 Agent + 返回结果。"""
        from orbit.agents.context import AgentResult

        class MockAgent:
            def __init__(self):
                self.message_bus = None
                self.tool_registry = None
                self.llm_client = None

            async def run(self, ctx: TaskContext) -> AgentResult:
                return AgentResult(success=True, output="mock done", duration_ms=10)

        class MockFactory:
            def create(self, role: str):
                return MockAgent()

        sched = Scheduler(agent_factory=MockFactory())
        output = await sched._run_agent("developer", "t1", {"prd": "test"})
        assert "mock done" in output

    @pytest.mark.asyncio
    async def test_run_agent_timeout(self) -> None:
        """Agent 超时 → 返回 timeout 标记。"""
        import asyncio

        from orbit.agents.context import AgentResult

        class SlowAgent:
            message_bus = None
            tool_registry = None
            llm_client = None

            async def run(self, ctx: TaskContext) -> AgentResult:
                await asyncio.sleep(999)  # 不会醒来
                return AgentResult(success=True)

        class SlowFactory:
            def create(self, role: str):
                return SlowAgent()

        sched = Scheduler(agent_factory=SlowFactory())
        output = await sched._run_agent("developer", "t1", {}, timeout=0.05)
        assert "timeout" in output.lower()

    @pytest.mark.asyncio
    async def test_dependency_injection(self) -> None:
        """Agent 收到注入的 MessageBus + ToolRegistry。"""
        from orbit.agents.context import AgentResult

        injected = {}

        class CheckAgent:
            def __init__(self):
                self.message_bus = None
                self.tool_registry = None
                self.llm_client = None

            async def run(self, ctx: TaskContext) -> AgentResult:
                injected["bus"] = self.message_bus
                injected["tools"] = self.tool_registry
                injected["llm"] = self.llm_client
                return AgentResult(success=True)

        class CheckFactory:
            def create(self, role: str):
                return CheckAgent()

        sched = Scheduler(
            agent_factory=CheckFactory(),
            message_bus="fake-bus",
            tool_registry="fake-tools",
            llm_client="fake-llm",
        )
        await sched._run_agent("developer", "t1", {})
        assert injected["bus"] == "fake-bus"
        assert injected["tools"] == "fake-tools"
        assert injected["llm"] == "fake-llm"
