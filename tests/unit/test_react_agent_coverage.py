"""ReActAgent coverage expansion — 66%→85% target.

Focus:
  - __init__ task_keywords parameter
  - _task_keywords getattr safety
  - DecisionLog integration (lazy init, query, record)
  - GoalJudge interaction (not_ok inject, fail-open)
  - MAX_TURNS exit path
  - _truncate_output module-level function
  - IterationBudget consumed in ReAct loop
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.agents.base import AgentInput, AgentRole
from orbit.agents.react_agent import IterationBudget, ReActAgent, _truncate_output
from orbit.goal_judge.models import Verdict
from orbit.memory.decision_log import Decision
from orbit.stream.events import StreamEventType
from tests.e2e.mock_llm import MockLLMClient


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def mock_tools():
    """Mock ToolRegistry——复用已有测试模式."""
    tools = MagicMock()
    tools.get_schemas.return_value = []
    tools.list_for_role.return_value = []
    tools.would_form_loop.return_value = False
    tools.dispatch = AsyncMock(return_value="mock result")
    tools.record_tool_call = MagicMock()
    return tools


# ── _task_keywords ──────────────────────────────────────


class TestTaskKeywords:
    """_task_keywords 模板匹配关键词——getattr 安全 + 上下文注入."""

    def test_init_stores_task_keywords(self, mock_tools):
        """Constructor stores the provided task_keywords list."""
        llm = AsyncMock()

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools, task_keywords=["redis", "cache"])
        assert agent._task_keywords == ["redis", "cache"]

    def test_init_defaults_empty(self, mock_tools):
        """Constructor defaults to [] when task_keywords not provided."""
        llm = AsyncMock()

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools)
        assert agent._task_keywords == []

    @pytest.mark.asyncio
    async def test_getattr_safety_without_attribute(self):
        """No _task_keywords attr → getattr returns None → execute_stream safe."""
        agent = ReActAgent.__new__(ReActAgent)
        agent.role = AgentRole.DEVELOPER
        agent.llm = None
        agent.tools = MagicMock()
        agent._event_bus = None
        agent._budget = IterationBudget(90)
        agent._compressor = None
        agent._budget_tracker = None
        agent._goal = None
        agent._goal_judge = None
        agent._decision_log = None
        # 不设置 _task_keywords → getattr(self, "_task_keywords", None) 返回 None

        events: list = []
        async for event in agent.execute_stream(AgentInput(task="test")):
            events.append(event)

        assert len(events) == 1
        assert events[0].type == StreamEventType.FINISH_STEP

    @pytest.mark.asyncio
    async def test_keywords_injected_to_context(self, mock_tools):
        """task_keywords injected into input_data.context['keywords']."""
        mock_llm = MockLLMClient(fixed_response="task complete")

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=mock_llm, tools=mock_tools, task_keywords=["redis", "cache"])
        input_data = AgentInput(task="test", context={"task_id": "t1"})
        result = await agent.execute(input_data)

        assert result.status == "ok"
        assert input_data.context.get("keywords") == ["redis", "cache"]


# ── DecisionLog ──────────────────────────────────────────


class TestDecisionLog:
    """决策日志集成——懒初始化 + fail-open + 查询注入 + [DECISION] 记录."""

    @patch("orbit.agents.react_agent.DecisionLog")
    def test_get_decision_log_lazy_init(self, mock_decision_log_cls):
        """_get_decision_log creates DecisionLog on first call, caches subsequent."""
        mock_instance = MagicMock()
        mock_decision_log_cls.return_value = mock_instance

        agent = ReActAgent.__new__(ReActAgent)
        agent._decision_log = None

        # 首次调用 → 创建
        result = agent._get_decision_log()
        assert result is mock_instance
        mock_decision_log_cls.assert_called_once()

        # 再次调用 → 返回缓存
        result2 = agent._get_decision_log()
        assert result2 is mock_instance
        assert mock_decision_log_cls.call_count == 1

    @patch("orbit.agents.react_agent.DecisionLog")
    def test_get_decision_log_fail_open(self, mock_decision_log_cls):
        """_get_decision_log returns None when DecisionLog() raises."""
        mock_decision_log_cls.side_effect = OSError("disk full or permission denied")

        agent = ReActAgent.__new__(ReActAgent)
        agent._decision_log = None

        result = agent._get_decision_log()
        assert result is None

    @pytest.mark.asyncio
    async def test_decision_query_attached_to_system_prompt(self, mock_tools):
        """Past decisions injected into system prompt."""
        captured_reqs: list = []

        llm = AsyncMock()

        async def mock_stream(req, task_id="", agent_name=""):
            captured_reqs.append(req)
            yield (StreamEventType.TEXT_DELTA, {"delta": "done"})

        llm.generate_stream_with_tools = mock_stream

        mock_dlog = MagicMock()
        mock_dlog.query.return_value = [
            Decision(
                question="缓存方案选型",
                answer="Redis",
                alternatives=["Memcached"],
                rationale="需要持久化+高可用",
                agent="developer",
                task_id="t1",
                timestamp=1000.0,
            ),
        ]

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools, task_keywords=["cache"])
        agent._decision_log = mock_dlog

        result = await agent.execute(AgentInput(task="test cache", context={"task_id": "t1"}))
        assert result.status == "ok"
        assert len(captured_reqs) >= 1
        # 历史决策追加到 system_prompt 尾部
        assert "相关历史决策" in captured_reqs[0].system_prompt
        assert "Redis" in captured_reqs[0].system_prompt

    @pytest.mark.asyncio
    async def test_decision_marker_triggers_record(self, mock_tools):
        """[DECISION] marker in LLM output triggers dlog.record()."""
        mock_dlog = MagicMock()
        mock_dlog.query.return_value = []

        llm = AsyncMock()

        async def mock_stream(req, task_id="", agent_name=""):
            yield (
                StreamEventType.TEXT_DELTA,
                {
                    "delta": (
                        "I'll use Redis.\n\n"
                        "[DECISION] Q: 缓存方案选型\n"
                        "A: Redis\n"
                        "Alternatives: Memcached\n"
                        "Rationale: 需要持久化"
                    )
                },
            )

        llm.generate_stream_with_tools = mock_stream

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=llm, tools=mock_tools, task_keywords=["cache"])
        agent._decision_log = mock_dlog

        result = await agent.execute(AgentInput(task="choose cache", context={"task_id": "t1"}))
        assert result.status == "ok"
        mock_dlog.record.assert_called_once()


# ── MAX_TURNS ────────────────────────────────────────────


class TestMaxTurns:
    """步数上限——LLM 一直返回 tool_call 达 MAX_TURNS."""

    @pytest.mark.asyncio
    async def test_max_turns_exceeded(self):
        """Loop reaches MAX_TURNS → ERROR event with MAX_TURNS code."""
        tool_call_event = (
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

        llm = AsyncMock()

        async def mock_stream(req, task_id="", agent_name=""):
            yield tool_call_event

        llm.generate_stream_with_tools = mock_stream

        tools = MagicMock()
        tools.get_schemas.return_value = []
        tools.list_for_role.return_value = [{"name": "read_file"}]
        tools.would_form_loop.return_value = False
        tools.dispatch = AsyncMock(return_value="file content")
        tools.record_tool_call = MagicMock()

        class QuickAgent(ReActAgent):
            role = AgentRole.DEVELOPER
            MAX_TURNS = 3

        agent = QuickAgent(llm=llm, tools=tools)

        result = await agent.execute(AgentInput(task="test", context={"task_id": "t1"}))
        assert result.status == "error"
        assert "MAX_TURNS" in str(result.result.get("code", ""))

    @pytest.mark.asyncio
    async def test_budget_consumed_on_tool_call(self):
        """Each tool call consumes IterationBudget in the ReAct loop."""
        llm = AsyncMock()

        async def mock_stream(req, task_id="", agent_name=""):
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

        llm.generate_stream_with_tools = mock_stream

        tools = MagicMock()
        tools.get_schemas.return_value = []
        tools.list_for_role.return_value = [{"name": "read_file"}]
        tools.would_form_loop.return_value = False
        tools.dispatch = AsyncMock(return_value="content")
        tools.record_tool_call = MagicMock()

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER
            MAX_TURNS = 2

        agent = TestAgent(llm=llm, tools=tools)
        consumed_before = agent._budget.total - agent._budget.remaining

        result = await agent.execute(AgentInput(task="test", context={"task_id": "t1"}))
        consumed_after = agent._budget.total - agent._budget.remaining

        # 2 轮，各 1 个 tool_call → consumed 增 2
        assert consumed_after - consumed_before == 2
        assert result.status == "error"  # hit MAX_TURNS


# ── _truncate_output ─────────────────────────────────────


class TestTruncateOutput:
    """_truncate_output 模块级函数——头尾 + 中间摘要."""

    @pytest.mark.parametrize(
        ("text", "max_chars", "expected"),
        [
            ("short text", 100, "short text"),
            ("", 100, ""),
            ("a" * 10, 20, "a" * 10),
        ],
    )
    def test_no_truncation(self, text: str, max_chars: int, expected: str) -> None:
        assert _truncate_output(text, max_chars) == expected

    def test_long_string_truncated(self) -> None:
        """String exceeding max_chars → head + gap notice + tail."""
        max_chars = 50
        text = "A" * 200
        result = _truncate_output(text, max_chars)
        assert len(result) < len(text)
        assert "截断" in result
        assert "... [截断 " in result

    def test_exact_boundary(self) -> None:
        """String exactly at max_chars → unchanged."""
        text = "B" * 100
        result = _truncate_output(text, 100)
        assert result == text


# ── GoalJudge ────────────────────────────────────────────


class TestGoalJudge:
    """Phase 4 AC-B1: GoalJudge 自检——not_ok 注入消息 + 异常 fail-open."""

    @pytest.mark.asyncio
    async def test_not_ok_injects_user_message(self, mock_tools):
        """GoalJudge not_ok → THINKING event → user msg → loop continues → finish."""
        goal = MagicMock()
        goal_judge = MagicMock()

        judge_call_count = [0]

        async def mock_evaluate(goal_param, transcript="", task_id=""):
            judge_call_count[0] += 1
            if judge_call_count[0] == 1:
                return Verdict(ok=False, reason="缺少测试覆盖", suggestions=["加单元测试"])
            return Verdict(ok=True, reason="全部覆盖")

        goal_judge.evaluate = mock_evaluate
        mock_llm = MockLLMClient(fixed_response="partial work")

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER
            MAX_TURNS = 5

        agent = TestAgent(llm=mock_llm, tools=mock_tools, goal=goal, goal_judge=goal_judge)

        events: list = []
        async for event in agent.execute_stream(
            AgentInput(task="test coverage", context={"task_id": "t1"})
        ):
            events.append(event)

        # not_ok → THINKING 事件含 verdict reason
        thinking_events = [e for e in events if e.type == StreamEventType.THINKING]
        assert len(thinking_events) >= 1
        assert "缺少测试覆盖" in thinking_events[0].data.get("content", "")

        # 最终正常完成（FINISH_STEP）
        finish_events = [e for e in events if e.type == StreamEventType.FINISH_STEP]
        assert len(finish_events) >= 1

        # Judge 被调用至少两次（not_ok → ok）
        assert judge_call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_exception_fail_open(self, mock_tools):
        """GoalJudge raises → warning logged → verdict None → skip → normal finish."""
        goal = MagicMock()
        goal_judge = MagicMock()

        async def mock_evaluate(goal_param, transcript="", task_id=""):
            raise RuntimeError("judge crashed")

        goal_judge.evaluate = mock_evaluate
        mock_llm = MockLLMClient(fixed_response="done")

        class TestAgent(ReActAgent):
            role = AgentRole.DEVELOPER

        agent = TestAgent(llm=mock_llm, tools=mock_tools, goal=goal, goal_judge=goal_judge)

        # 异常不应阻断 Agent——fail-open 正常完成
        result = await agent.execute(AgentInput(task="test", context={"task_id": "t1"}))
        assert result.status == "ok"
