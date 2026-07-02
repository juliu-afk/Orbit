"""覆盖率深度补测——gateway/client 纯函数路径 + goal_judge/judge + scheduler/task_runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.gateway.client import LLMClient
from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage
from orbit.goal_judge.judge import GoalJudge
from orbit.goal_judge.models import Goal, Verdict
from orbit.scheduler.task_runner import TaskRunner


# ════════════════════════════════════════════
# 1. LLMClient 纯函数
# ════════════════════════════════════════════

class TestLLMClientDeep:
    def test_init_with_model(self):
        client = LLMClient(default_model="gpt-4")
        assert client.default_model == "gpt-4"

    def test_get_usage_stats_initial(self):
        client = LLMClient()
        stats = client.get_usage_stats("nonexistent")
        assert stats is not None

    def test_response_with_usage(self):
        usage = LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        resp = LLMResponse(
            content="test response", model="test-model",
            usage=usage,
        )
        assert resp.usage.prompt_tokens == 100

    def test_request_with_tool_choice(self):
        req = LLMRequest(
            prompt="read a file", tool_choice="auto",
            tools=[{"name": "read_file"}],
        )
        assert req.tool_choice == "auto"
        assert len(req.tools) == 1

    def test_request_with_messages(self):
        req = LLMRequest(
            prompt="continue",
            messages=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )
        assert len(req.messages) == 2

    def test_request_provider(self):
        req = LLMRequest(prompt="test", provider="openai")
        assert req.provider == "openai"


# ════════════════════════════════════════════
# 2. GoalJudge
# ════════════════════════════════════════════

class TestGoalJudgeDeep:
    def test_init(self):
        judge = GoalJudge()
        assert judge.llm is None
        assert judge.registry is None

    def test_init_with_llm(self):
        mock_llm = MagicMock()
        judge = GoalJudge(llm=mock_llm)
        assert judge.llm is mock_llm

    @pytest.mark.asyncio
    async def test_evaluate_without_llm(self):
        """无 LLM → fail-open (ok=True)。"""
        judge = GoalJudge(llm=None)
        goal = Goal(description="build app")
        verdict = await judge.evaluate(goal, transcript="done", task_id="t1")
        assert isinstance(verdict, Verdict)
        assert verdict.ok is True  # fail-open

    @pytest.mark.asyncio
    async def test_evaluate_with_llm(self):
        """有 LLM → 正常判定。"""
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            content='{"ok": false, "reason": "not done yet", "impossible": false}',
        ))
        judge = GoalJudge(llm=mock_llm)
        goal = Goal(description="build complex system")
        verdict = await judge.evaluate(goal, transcript="partial", task_id="t2")
        assert verdict.ok is False


# ════════════════════════════════════════════
# 3. TaskRunner 额外路径
# ════════════════════════════════════════════

class TestTaskRunnerDeep:
    def test_extract_keywords_empty(self):
        kw = TaskRunner._extract_keywords("")
        assert kw == []

    def test_extract_keywords_english_only(self):
        kw = TaskRunner._extract_keywords("Implement UserAuthentication with JWT tokens")
        assert "UserAuthentication" in kw
        assert "JWT" in kw

    def test_extract_keywords_stop_words(self):
        """停用词被过滤。"""
        kw = TaskRunner._extract_keywords("修改 VoucherForm 的方法")
        # "修改" 和 "的" 是停用词
        assert "修改" not in kw
        assert "的" not in kw
