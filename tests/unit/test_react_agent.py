"""ReActAgent 单元测试——think→act→observe 循环.

Phase 1 AC6-AC8 验收测试.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from orbit.agents.react_agent import IterationBudget, ReActAgent, _truncate_output


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def mock_llm():
    """模拟 LLM——第一次返回 tool_call，第二次返回完成."""
    llm = AsyncMock()
    # 第一次调用→ tool_calls (read_file)
    # 第二次调用→ end_turn (完成)
    from orbit.gateway.schemas import LLMResponse, LLMUsage

    responses = [
        LLMResponse(
            content="",
            model="mock",
            usage=LLMUsage(),
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "test.py"}',
                    },
                }
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(
            content="代码审查完成，发现 2 个问题。",
            model="mock",
            usage=LLMUsage(),
            stop_reason="end_turn",
        ),
    ]
    llm.generate = AsyncMock(side_effect=responses)
    return llm


@pytest.fixture
def mock_tools():
    """模拟 ToolRegistry."""
    tools = MagicMock()
    tools.get_schemas.return_value = []
    tools.would_form_loop.return_value = False
    tools.dispatch = AsyncMock(return_value="# test.py (line 1-10)\n1\tdef foo():\n2\t    pass\n")
    return tools


@pytest.fixture
def react_agent(mock_llm, mock_tools):
    """创建用于测试的 ReActAgent 子类."""
    class TestAgent(ReActAgent):
        role = AgentRole.DEVELOPER

    return TestAgent(llm=mock_llm, tools=mock_tools)


# ── IterationBudget ───────────────────────────────────


class TestIterationBudget:
    """迭代预算——对标 Hermes iteration_budget."""

    def test_initial_remaining(self):
        budget = IterationBudget(90)
        assert budget.remaining == 90

    def test_consume(self):
        budget = IterationBudget(10)
        assert budget.consume(3)
        assert budget.remaining == 7

    def test_exhausted(self):
        budget = IterationBudget(5)
        # 消费 5 次——刚好用完
        assert budget.consume(5)
        assert budget.remaining == 0
        # 再消费——超出
        assert not budget.consume(1)

    def test_default_total(self):
        budget = IterationBudget()
        assert budget.total == 90


# ── ReActAgent 核心 ────────────────────────────────────


class TestReActAgentCore:
    """AC6-AC8: ReAct 循环执行."""

    def test_agent_has_tools(self, react_agent, mock_tools):
        """Agent 注入了工具注册表."""
        assert react_agent.tools is mock_tools

    @pytest.mark.asyncio
    async def test_execute_react_loop(self, react_agent, mock_llm, mock_tools):
        """完整的 ReAct 循环——tool_calls → dispatch → end_turn."""
        input_data = AgentInput(
            task="审查 test.py 的质量",
            context={"task_id": "test-001"},
        )
        result = await react_agent.execute(input_data)

        # 调用了 LLM 两次
        assert mock_llm.generate.call_count == 2
        # 调用了工具一次
        mock_tools.dispatch.assert_called_once()
        # 返回成功
        assert result.status == "ok"
        # 推理链记录了 2 轮
        assert len(result.result["reasoning_chain"]) == 2
        assert result.result["turns"] == 2
        assert result.result["tool_calls"] == 1

    @pytest.mark.asyncio
    async def test_execute_mock_mode(self, mock_tools):
        """无 LLM 连接——返回 mock 结果."""
        agent = ReActAgent.__new__(ReActAgent)
        agent.role = AgentRole.DEVELOPER
        agent.llm = None
        agent.tools = mock_tools
        agent._event_bus = None
        agent._budget = IterationBudget(90)

        input_data = AgentInput(task="test")
        result = await agent.execute(input_data)
        assert result.status == "ok"
        assert "mock" in str(result.result).lower()

    @pytest.mark.asyncio
    async def test_doom_loop_detected(self, mock_tools):
        """Doom Loop 前置检测生效——第3次被拦截."""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        mock_tools.would_form_loop.side_effect = [False, False, True]
        mock_tools.dispatch = AsyncMock(return_value="result")

        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=[
            # Turn 0: tool_call——通过 doom check，执行
            LLMResponse(
                content="", model="mock", usage=LLMUsage(),
                tool_calls=[{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a.py"}'}}],
                stop_reason="tool_calls",
            ),
            # Turn 1: tool_call again——通过 doom check（不同args），执行
            LLMResponse(
                content="", model="mock", usage=LLMUsage(),
                tool_calls=[{"id": "c2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"b.py"}'}}],
                stop_reason="tool_calls",
            ),
            # Turn 2: tool_call——doom loop! → 跳过，注入警告，继续到 LLM
            LLMResponse(
                content="", model="mock", usage=LLMUsage(),
                tool_calls=[{"id": "c3", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"a.py"}'}}],
                stop_reason="tool_calls",
            ),
            # Turn 3: end_turn (LLM 收到死循环警告后决定完成)
            LLMResponse(
                content="无法继续——系统检测到死循环。", model="mock", usage=LLMUsage(),
                stop_reason="end_turn",
            ),
        ])

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test", context={"task_id": "t1"}))

        assert result.status == "ok"
        # dispatch 调用了 2 次（第 3 次被 doom loop 阻止）
        assert mock_tools.dispatch.call_count == 2


# ── 输出截断 ──────────────────────────────────────────


class TestOutputTruncation:
    """AC6b: >10K chars 截断."""

    def test_short_not_truncated(self):
        result = _truncate_output("hello world", 100)
        assert result == "hello world"
        assert "截断" not in result

    def test_long_truncated(self):
        long_text = "x" * 15000
        result = _truncate_output(long_text, 10000)
        assert len(result) <= 10500  # 10K + 截断标记
        assert "截断" in result

    def test_exact_boundary(self):
        text = "a" * 10000
        result = _truncate_output(text, 10000)
        assert result == text  # 刚好 10K 不截断


# ── 退出条件 ──────────────────────────────────────────


class TestExitConditions:
    """AC8: 4 种退出条件."""

    @pytest.mark.asyncio
    async def test_normal_completion(self, mock_tools):
        """正常完成——stop_reason=end_turn."""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=LLMResponse(
            content="任务完成", model="mock", usage=LLMUsage(), stop_reason="end_turn",
        ))

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "ok"
        assert "完成" in str(result.result)

    @pytest.mark.asyncio
    async def test_max_tokens_stop(self, mock_tools):
        """token 截断——stop_reason=max_tokens."""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=LLMResponse(
            content="输出被截断前的内容...", model="mock", usage=LLMUsage(),
            stop_reason="max_tokens",
        ))

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "ok"
        assert "截断" in str(result.result.get("warning", ""))

    @pytest.mark.asyncio
    async def test_error_stop(self, mock_tools):
        """LLM 错误——stop_reason=error."""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        llm = AsyncMock()
        llm.generate = AsyncMock(return_value=LLMResponse(
            content="服务不可用", model="mock", usage=LLMUsage(), stop_reason="error",
        ))

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "error"


# ── MAX_TURNS 配置 ────────────────────────────────────


class TestAgentConfig:
    """Agent 的 MAX_TURNS 覆盖."""

    def test_default_max_turns(self):
        class DefaultAgent(ReActAgent):
            role = AgentRole.DEVELOPER
        assert DefaultAgent.MAX_TURNS == 20

    def test_custom_max_turns(self):
        class FastAgent(ReActAgent):
            role = AgentRole.REVIEWER
            MAX_TURNS = 5
        assert FastAgent.MAX_TURNS == 5
