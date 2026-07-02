"""覆盖率补测——goal 子模块扩展 (critique + verifier + preflight + compose_bridge)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.goal.critique import (
    CRITIQUE_DIMENSIONS,
    CRITIQUE_SYSTEM_PROMPT,
    CritiqueAgent,
    CritiqueIssue,
    CritiqueResult,
)
from orbit.goal.compose_bridge import GoalComposeBridge
from orbit.goal.preflight import PreFlightEstimator, PreFlightResult
from orbit.goal.verifier import CommandNotAllowedError, ExecutorVerifier, VerificationResult


# ════════════════════════════════════════════
# 1. CritiqueIssue + CritiqueResult
# ════════════════════════════════════════════

class TestCritiqueResult:
    def test_max_severity_none_when_no_issues(self):
        """无问题 → max_severity='none'。"""
        result = CritiqueResult(approved=True)
        assert result.max_severity == "none"

    def test_max_severity_critical_first(self):
        """critical > major > minor 优先级。"""
        result = CritiqueResult(
            approved=False,
            issues=[
                CritiqueIssue("minor", "security", "minor issue"),
                CritiqueIssue("critical", "correctness", "critical bug"),
                CritiqueIssue("major", "performance", "major issue"),
            ],
        )
        assert result.max_severity == "critical"

    def test_max_severity_major(self):
        """无 critical 时返回 major。"""
        result = CritiqueResult(
            approved=False,
            issues=[
                CritiqueIssue("major", "security", "xss"),
                CritiqueIssue("minor", "performance", "slow"),
            ],
        )
        assert result.max_severity == "major"

    def test_issue_count_by_severity(self):
        """统计各严重程度的问题数。"""
        result = CritiqueResult(
            approved=False,
            issues=[
                CritiqueIssue("critical", "correctness", "a"),
                CritiqueIssue("critical", "security", "b"),
                CritiqueIssue("minor", "maintainability", "c"),
            ],
        )
        counts = result.issue_count_by_severity
        assert counts["critical"] == 2
        assert counts["minor"] == 1

    def test_critique_issue_default_location(self):
        """CritiqueIssue 默认 location 为空。"""
        issue = CritiqueIssue("major", "performance", "N+1 query")
        assert issue.location == ""
        assert issue.severity == "major"
        assert issue.dimension == "performance"


# ════════════════════════════════════════════
# 2. CritiqueAgent — 纯函数方法
# ════════════════════════════════════════════

class TestCritiqueAgentPure:
    def test_parse_response_valid_json(self):
        """解析合法 JSON 批判响应。"""
        agent = CritiqueAgent()
        response = """{
            "approved": false,
            "issues": [{"severity": "critical", "dimension": "security", "description": "SQL injection"}],
            "summary": "found 1 critical issue"
        }"""
        result = agent._parse_response(response)
        assert result.approved is False
        assert len(result.issues) == 1
        assert result.issues[0].severity == "critical"
        assert result.summary == "found 1 critical issue"

    def test_parse_response_markdown_code_block(self):
        """解析被 ```json 包裹的响应。"""
        agent = CritiqueAgent()
        response = """```json
        {"approved": true, "issues": [], "summary": "all good"}
        ```"""
        result = agent._parse_response(response)
        assert result.approved is True

    def test_parse_response_invalid_json_fail_open(self):
        """解析失败 → fail-open (approved=True)。"""
        agent = CritiqueAgent()
        result = agent._parse_response("not json at all")
        assert result.approved is True
        assert "解析失败" in result.summary

    def test_parse_response_default_approved_true(self):
        """JSON 无 approved 字段 → 默认 True。"""
        agent = CritiqueAgent()
        result = agent._parse_response('{"issues": [], "summary": ""}')
        assert result.approved is True

    def test_format_verification(self):
        """格式化验证结果列表。"""
        results = [
            {"command": "pytest", "passed": True, "exit_code": 0},
            {"command": "mypy", "passed": False, "exit_code": 1},
        ]
        output = CritiqueAgent._format_verification(results)
        assert "pytest" in output
        assert "mypy" in output
        assert "✅" in output
        assert "❌" in output

    def test_format_alternatives(self):
        """格式化集成候选方案。"""
        alts = [
            {"model": "claude-opus", "output": "def foo():"},
            {"model": "gpt-4o", "output": "async def foo():"},
        ]
        output = CritiqueAgent._format_alternatives(alts)
        assert "方案 1" in output
        assert "claude-opus" in output
        assert "方案 2" in output

    def test_generator_to_critic_model_map(self):
        """跨模型批判映射表正确。"""
        m = CritiqueAgent.GENERATOR_TO_CRITIC_MODEL
        assert m["anthropic"] == "openai"
        assert m["openai"] == "anthropic"
        assert m["glm"] == "anthropic"

    def test_critique_mock_mode_no_llm(self):
        """无 LLM → mock mode 自动通过。"""
        agent = CritiqueAgent(llm=None)

        async def _run():
            return await agent.critique(MagicMock(), code_artifact="code")

        import asyncio
        result = asyncio.run(_run())
        assert result.approved is True
        assert "mock" in result.summary.lower()


# ════════════════════════════════════════════
# 3. CritiqueAgent — critique 完整路径
# ════════════════════════════════════════════

class TestCritiqueAgentWithLLM:
    @pytest.mark.asyncio
    async def test_critique_large_code_truncated(self):
        """超长代码 → 截断到 10000 字符。"""
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            content='{"approved": true, "issues": [], "summary": "ok"}'
        ))

        agent = CritiqueAgent(llm=mock_llm)
        task = MagicMock()
        task.description = "test task"
        long_code = "x" * 15000
        await agent.critique(task, code_artifact=long_code)

        # 验证传递给 LLM 的 prompt 已截断
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0].prompt
        assert "截断" in prompt

    @pytest.mark.asyncio
    async def test_critique_llm_failure_fail_open(self):
        """LLM 调用失败 → fail-open。"""
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("network down"))

        agent = CritiqueAgent(llm=mock_llm)
        task = MagicMock()
        task.description = "test"
        result = await agent.critique(task, code_artifact="code")
        assert result.approved is True
        assert "fail-open" in result.summary

    @pytest.mark.asyncio
    async def test_critique_includes_verification_results(self):
        """critique 可包含验证结果。"""
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            content='{"approved": false, "issues": [], "summary": "verif failed"}'
        ))

        agent = CritiqueAgent(llm=mock_llm)
        task = MagicMock()
        task.description = "test"
        await agent.critique(
            task,
            verification_results=[{"command": "pytest", "passed": False, "exit_code": 1}],
        )
        call_args = mock_llm.generate.call_args
        prompt = call_args[0][0].prompt
        assert "pytest" in prompt


# ════════════════════════════════════════════
# 4. 常量
# ════════════════════════════════════════════

class TestConstants:
    def test_critique_dimensions_sum_to_100(self):
        """批判维度权重合计约为 1.0。"""
        total = sum(d["weight"] for d in CRITIQUE_DIMENSIONS.values())
        assert 0.99 <= total <= 1.01

    def test_critique_system_prompt_not_empty(self):
        """批判系统提示词非空。"""
        assert len(CRITIQUE_SYSTEM_PROMPT) > 50


# ════════════════════════════════════════════
# 5. Verifier
# ════════════════════════════════════════════

class TestExecutorVerifier:
    @pytest.mark.asyncio
    async def test_execute_empty_commands(self):
        """无验证命令 → 返回空结果。"""
        verifier = ExecutorVerifier()
        result = await verifier.execute([])
        assert result.total_count == 0
        assert result.passed_count == 0

    @pytest.mark.asyncio
    async def test_validate_commands_shell_metachar(self):
        """shell 元字符 → CommandNotAllowedError。"""
        verifier = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            verifier._validate_commands(["cat file.txt; rm -rf /"])

    @pytest.mark.asyncio
    async def test_validate_commands_unknown_cmd(self):
        """不在白名单的命令 → CommandNotAllowedError。"""
        verifier = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            verifier._validate_commands(["rm -rf /"])

    def test_verification_result_properties(self):
        """VerificationResult 属性正确。"""
        result = VerificationResult(
            results=[
                {"command": "ls", "exit_code": 0, "passed": True},
                {"command": "cat /nonexistent", "exit_code": 1, "passed": False, "stderr_tail": "not found"},
            ]
        )
        assert result.total_count == 2
        assert result.passed_count == 1
        assert len(result.failed_commands) == 1
        assert result.all_passed is True  # 构造时设为 True——由 execute() 更新

    def test_to_prompt_section_empty(self):
        """空结果 → 默认提示。"""
        result = VerificationResult()
        section = result.to_prompt_section()
        assert "无验证命令" in section

    def test_to_prompt_section_with_results(self):
        """有结果 → 格式化含 ✅/❌。"""
        result = VerificationResult(
            results=[{"command": "pytest", "exit_code": 0, "passed": True}]
        )
        section = result.to_prompt_section()
        assert "pytest" in section
        assert "✅" in section


# ════════════════════════════════════════════
# 6. PreFlightEstimator
# ════════════════════════════════════════════

class TestPreFlightEstimator:
    @pytest.mark.asyncio
    async def test_estimate_returns_valid_result(self):
        """estimate() 返回 PreFlightResult。"""
        estimator = PreFlightEstimator()
        result = await estimator.estimate("构建计算器应用")
        assert result.token_low > 0
        assert result.token_high >= result.token_low
        assert result.time_low_seconds > 0
        assert result.time_high_seconds >= result.time_low_seconds
        assert 0 <= result.confidence <= 1
        assert result.source in ("fuzzy", "kb")

    @pytest.mark.asyncio
    async def test_estimate_with_features(self):
        """复杂描述的估计值 >= 简单描述。"""
        estimator = PreFlightEstimator()
        simple = await estimator.estimate("简单计算器")
        complex_result = await estimator.estimate(
            "构建一个全栈电商平台，包含用户认证、商品管理、购物车、支付集成、订单追踪、库存管理、推荐系统"
        )
        assert complex_result.token_high >= simple.token_high

    @pytest.mark.asyncio
    async def test_estimate_empty_prd(self):
        """空 PRD → 返回基线估计。"""
        estimator = PreFlightEstimator()
        result = await estimator.estimate("")
        assert result.token_low > 0

    def test_preflight_result_dataclass(self):
        """PreFlightResult 有默认值。"""
        r = PreFlightResult()
        assert r.token_low == 50000
        assert r.source == "fuzzy"
        assert r.confidence == 0.5


# ════════════════════════════════════════════
# 7. GoalComposeBridge
# ════════════════════════════════════════════

class TestGoalComposeBridge:
    def test_bridge_init(self):
        """Bridge 初始化成功。"""
        bridge = GoalComposeBridge(llm=MagicMock())
        assert bridge._llm is not None

    @pytest.mark.asyncio
    async def test_generate_spec_returns_result(self):
        """generate_spec() 返回 spec 对象。"""
        bridge = GoalComposeBridge(llm=MagicMock())
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = MagicMock(content='{"tasks": [{"id": "1", "description": "task1"}]}')
        bridge._llm = mock_llm

        goal = MagicMock()
        goal.description = "构建用户认证系统"
        goal.constraints = []
        goal.sub_tasks = {}

        result = await bridge.generate_spec(goal)
        # 无 LLM 时返回 mock spec，有 LLM 时返回解析结果
        assert result is not None

    def test_filter_pending_tasks_dict_path(self):
        """filter_pending_tasks() dict 路径——过滤已完成任务。"""
        bridge = GoalComposeBridge(llm=None)
        spec = {
            "title": "test",
            "description": "test spec",
            "tasks": [
                {"id": "1", "description": "task1"},
                {"id": "2", "description": "task2"},
            ],
        }
        progress = {"1": "done", "2": "active"}
        result = bridge.filter_pending_tasks(spec, progress)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["id"] == "2"

    def test_filter_pending_tasks_all_done(self):
        """filter_pending_tasks() dict 全部完成 → 返回空列表。"""
        bridge = GoalComposeBridge(llm=None)
        spec = {
            "tasks": [{"id": "1", "description": "task1"}],
        }
        progress = {"1": "done"}
        result = bridge.filter_pending_tasks(spec, progress)
        assert len(result["tasks"]) == 0
