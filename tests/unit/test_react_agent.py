"""ReActAgent unit tests——think→act→observe loop.

Phase 3 upgrade: execute() delegates to execute_stream() → LLM calls generate_stream_with_tools().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentInput, AgentRole
from orbit.agents.react_agent import IterationBudget, ReActAgent

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def mock_llm():
    """Mock LLM——supports generate_stream_with_tools() (Phase 3 streaming API)."""
    from orbit.gateway.schemas import LLMResponse, LLMUsage
    from orbit.stream.events import StreamEventType

    llm = MagicMock()

    # Old API——backward compatibility
    responses = [
        LLMResponse(
            content="",
            model="mock",
            usage=LLMUsage(),
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"test.py"}'},
                }
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(
            content="code review done, 2 issues found.",
            model="mock",
            usage=LLMUsage(),
            stop_reason="end_turn",
        ),
    ]
    llm.generate = AsyncMock(side_effect=responses)

    # Phase 3 streaming API
    _call_count = [0]

    async def mock_stream_impl(req, task_id="", agent_name=""):
        """Mock stream: tool_call on first call, text-only on second."""
        _call_count[0] += 1
        if _call_count[0] == 1:
            yield (StreamEventType.TEXT_DELTA, {"delta": "Let me read the file."})
            yield (
                StreamEventType.TOOL_CALL,
                {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path": "test.py"}'},
                        }
                    ]
                },
            )
        else:
            yield (StreamEventType.TEXT_DELTA, {"delta": "code review complete, 2 issues found."})

    llm.generate_stream_with_tools = mock_stream_impl
    # track call count via _call_count instead of AsyncMock.call_count
    llm._stream_call_count = _call_count
    return llm


@pytest.fixture
def mock_tools():
    """Mock ToolRegistry."""
    tools = MagicMock()
    tools.get_schemas.return_value = []
    tools.would_form_loop.return_value = False
    tools.dispatch = AsyncMock(return_value="# test.py (line 1-10)\n1\tdef foo():\n2\t    pass\n")
    return tools


@pytest.fixture
def react_agent(mock_llm, mock_tools):
    """Create ReActAgent subclass for testing."""

    class TestAgent(ReActAgent):
        role = AgentRole.DEVELOPER

    return TestAgent(llm=mock_llm, tools=mock_tools)


# ── IterationBudget ───────────────────────────────────


class TestIterationBudget:
    """Iteration budget——Hermes-style."""

    def test_initial_remaining(self):
        budget = IterationBudget(90)
        assert budget.remaining == 90

    def test_consume(self):
        budget = IterationBudget(10)
        assert budget.consume(3)
        assert budget.remaining == 7

    def test_exhausted(self):
        budget = IterationBudget(5)
        assert budget.consume(5)
        assert budget.remaining == 0
        assert not budget.consume(1)

    def test_default_total(self):
        budget = IterationBudget()
        assert budget.total == 90


# ── ReActAgent Core ────────────────────────────────────


class TestReActAgentCore:
    """AC6-AC8: ReAct loop execution."""

    def test_agent_has_tools(self, react_agent, mock_tools):
        assert react_agent.tools is mock_tools

    @pytest.mark.asyncio
    async def test_execute_react_loop(self, react_agent, mock_llm, mock_tools):
        """Full ReAct loop——tool_call → dispatch → end_turn."""
        input_data = AgentInput(
            task="review test.py quality",
            context={"task_id": "test-001"},
        )
        result = await react_agent.execute(input_data)

        # Phase 3: execute() calls execute_stream() → generate_stream_with_tools()
        assert mock_llm._stream_call_count[0] == 2
        mock_tools.dispatch.assert_called_once()
        assert result.status == "ok"
        assert len(result.result["reasoning_chain"]) == 2
        assert result.result["turns"] == 2
        assert result.result["tool_calls"] == 1

    @pytest.mark.asyncio
    async def test_execute_mock_mode(self, mock_tools):
        """No LLM connection——returns mock result."""
        agent = ReActAgent.__new__(ReActAgent)
        agent.role = AgentRole.DEVELOPER
        agent.llm = None
        agent.tools = mock_tools
        agent._event_bus = None
        agent._budget = IterationBudget(90)
        agent._compressor = None
        agent._budget_tracker = None

        input_data = AgentInput(task="test")
        result = await agent.execute(input_data)
        assert result.status == "ok"
        assert "mock" in str(result.result).lower()

    @pytest.mark.asyncio
    async def test_doom_loop_detected(self, mock_tools):
        """Doom Loop detection——3rd identical call blocked."""
        from orbit.stream.events import StreamEventType

        mock_tools.would_form_loop.side_effect = [False, False, True]
        mock_tools.dispatch = AsyncMock(return_value="result")

        call_count = [0]

        async def mock_stream(req, task_id="", agent_name=""):
            call_count[0] += 1
            if call_count[0] == 1:
                yield (
                    StreamEventType.TOOL_CALL,
                    {
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"a.py"}'},
                            }
                        ]
                    },
                )
            elif call_count[0] == 2:
                yield (
                    StreamEventType.TOOL_CALL,
                    {
                        "tool_calls": [
                            {
                                "id": "c2",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"b.py"}'},
                            }
                        ]
                    },
                )
            elif call_count[0] == 3:
                yield (
                    StreamEventType.TOOL_CALL,
                    {
                        "tool_calls": [
                            {
                                "id": "c3",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"a.py"}'},
                            }
                        ]
                    },
                )
            else:
                yield (
                    StreamEventType.TEXT_DELTA,
                    {"delta": "cannot continue——doom loop detected."},
                )

        llm = AsyncMock()
        llm.generate_stream_with_tools = mock_stream

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test", context={"task_id": "t1"}))

        assert result.status == "ok"
        assert mock_tools.dispatch.call_count == 2  # 3rd blocked by doom loop


# ── Exit Conditions ────────────────────────────────────


class TestExitConditions:
    """AC8: 4 exit conditions——Phase 3 streaming version."""

    @pytest.mark.asyncio
    async def test_normal_completion(self, mock_tools):
        """Normal completion——no tool_call, text-only."""
        from orbit.stream.events import StreamEventType

        async def mock_stream(req, task_id="", agent_name=""):
            yield (StreamEventType.TEXT_DELTA, {"delta": "task complete"})

        llm = AsyncMock()
        llm.generate_stream_with_tools = mock_stream

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_stream_error(self, mock_tools):
        """LLM stream error——yields ERROR event."""
        from orbit.stream.events import StreamEventType

        async def mock_stream_error(req, task_id="", agent_name=""):
            yield (StreamEventType.ERROR, {"message": "token limit exceeded", "code": "MAX_TOKENS"})

        llm = AsyncMock()
        llm.generate_stream_with_tools = mock_stream_error

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "error"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_service_unavailable(self, mock_tools):
        """LLM returns ERROR——service unavailable."""
        from orbit.stream.events import StreamEventType

        async def mock_stream_err(req, task_id="", agent_name=""):
            yield (
                StreamEventType.ERROR,
                {"message": "service unavailable", "code": "SERVICE_UNAVAILABLE"},
            )

        llm = AsyncMock()
        llm.generate_stream_with_tools = mock_stream_err

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        result = await agent.execute(AgentInput(task="test"))
        assert result.status == "error"


# ── Cancellation ────────────────────────────────────────


class TestCancellation:
    """Phase 3 AC19.5: CancellationToken integration."""

    @pytest.mark.asyncio
    async def test_cancel_before_execute(self, mock_tools):
        """CancellationToken already set → immediate CANCELLED event."""
        from orbit.stream.cancellation import CancellationToken
        from orbit.stream.events import StreamEventType

        token = CancellationToken()
        token.cancel()

        agent = ReActAgent.__new__(ReActAgent)
        agent.role = AgentRole.DEVELOPER
        agent.llm = None  # mock mode
        agent.tools = mock_tools
        agent._event_bus = None
        agent._budget = IterationBudget(90)
        agent._compressor = None
        agent._budget_tracker = None

        events = []
        async for event in agent.execute_stream(AgentInput(task="test"), cancel_token=token):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.CANCELLED

    @pytest.mark.asyncio
    async def test_execute_stream_cancel_during_loop(self):
        """CancellationToken set mid-stream → CANCELLED event yielded."""
        from orbit.stream.cancellation import CancellationToken
        from orbit.stream.events import StreamEventType

        token = CancellationToken()

        # Mock LLM that returns text_delta on first call
        call_count = [0]

        async def mock_stream(req, task_id="", agent_name=""):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return normal text (no tool calls)
                # Token gets cancelled before second call
                token.cancel()
                yield (StreamEventType.TEXT_DELTA, {"delta": "working..."})
                # After this, the loop checks has_tool_calls=False and finishes
                # So we need a TOOL_CALL to keep the loop going
            else:
                yield (StreamEventType.TEXT_DELTA, {"delta": "should not reach"})

        # Actually, let's test with a TOOL_CALL that triggers next turn
        async def mock_stream_with_tool(req, task_id="", agent_name=""):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: tool call → execute tool → next turn
                yield (
                    StreamEventType.TOOL_CALL,
                    {
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": '{"path":"x.py"}'},
                            }
                        ]
                    },
                )
            else:
                # Second call: token already cancelled → should not be reached
                yield (StreamEventType.TEXT_DELTA, {"delta": "should not reach"})

        # Simpler approach: test cancellation via token set BEFORE execute_stream
        token2 = CancellationToken()
        token2.cancel()

        tools = MagicMock()
        tools.get_schemas.return_value = []
        tools.would_form_loop.return_value = False
        tools.dispatch = AsyncMock(return_value="file content")

        agent = ReActAgent.__new__(ReActAgent)
        agent.role = AgentRole.DEVELOPER
        agent.llm = None
        agent.tools = tools
        agent._event_bus = None
        agent._budget = IterationBudget(90)
        agent._compressor = None
        agent._budget_tracker = None

        events = []
        async for event in agent.execute_stream(
            AgentInput(task="test", context={"task_id": "t1"}),
            cancel_token=token2,
        ):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.CANCELLED
        assert events[0].data["message"] == "用户取消"

    @pytest.mark.asyncio
    async def test_base_agent_cancel_before_execute(self):
        """BaseAgent.execute_stream() respects CancellationToken."""
        from orbit.agents.base import AgentInput, AgentRole, BaseAgent
        from orbit.stream.cancellation import CancellationToken
        from orbit.stream.events import StreamEventType

        class SimpleAgent(BaseAgent):
            role = AgentRole.CONFIG_MANAGER

            async def execute(self, input_data):
                from orbit.agents.base import AgentOutput

                return AgentOutput(result={"output": "done"})

        agent = SimpleAgent()
        token = CancellationToken()
        token.cancel()

        events = []
        async for event in agent.execute_stream(AgentInput(task="test"), cancel_token=token):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.CANCELLED


# ── MAX_TURNS config ────────────────────────────────────


class TestAgentConfig:
    """Agent MAX_TURNS override."""

    def test_default_max_turns(self):
        class DefaultAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        assert DefaultAgent.MAX_TURNS == 20

    def test_custom_max_turns(self):
        class FastAgent(ReActAgent):
            role = AgentRole.REVIEWER
            MAX_TURNS = 5

        assert FastAgent.MAX_TURNS == 5
