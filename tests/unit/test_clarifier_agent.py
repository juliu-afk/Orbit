"""需求澄清 Agent 接入单元测试（V1-V3 校验 + ClarifierAgent mock）.

覆盖技术方案边界 case V-1 到 V-8 及 A1/A3。
不测 LLM 真实调用（无 key），仅测校验逻辑和 mock 模式。
"""

from __future__ import annotations

import asyncio

import pytest

from orbit.agents.base import AgentInput
from orbit.agents.clarifier import (
    ClarifierAgent,
    StructuredPRD,
    ValidationResult,
    validate_prd,
)


# ---- V1-V3 校验 case ----

class TestValidatePrd:
    """validate_prd 分层校验（技术方案 V-1 到 V-8）。"""

    def test_v1_complete_prd_passes(self) -> None:
        """V-1: 三项完整且一致 → 通过。"""
        prd = StructuredPRD(
            goal="修复微信支付回调丢失",
            scope="做：新增补偿任务；不做：不改回调本身",
            acceptance_criteria=["5分钟未回调触发查单", "查到已支付则更新状态为成功"],
        )
        result = validate_prd(prd)
        assert result.passed is True
        assert result.failed_layer == ""

    def test_v1_goal_placeholder_fails(self) -> None:
        """V-2: goal=待定 → V1 失败。"""
        prd = StructuredPRD(
            goal="待定这是一个测试",
            scope="做：一个后台系统",
            acceptance_criteria=[],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V1"
        assert any("占位词" in r for r in result.reasons)

    def test_v1_scope_no_boundary_fails(self) -> None:
        """V-3: scope 无边界描述 → V1 失败。"""
        prd = StructuredPRD(
            goal="优化系统的性能表现",
            scope="一个非常复杂的后台系统",
            acceptance_criteria=["返回正确的结果"],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V1"

    def test_v1_empty_acceptance_fails(self) -> None:
        """V-4: acceptance=[] → V1 失败。"""
        prd = StructuredPRD(
            goal="修复支付模块的回调",
            scope="做：新增任务；不做：不改回调",
            acceptance_criteria=[],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V1"

    def test_v2_no_resonance_fails(self) -> None:
        """V-5: goal 谈支付但 scope/acceptance 无呼应 → V2 失败。"""
        prd = StructuredPRD(
            goal="修复支付模块的回调问题",
            scope="做：新增日志组件；不做：不改数据库",
            acceptance_criteria=["日志组件返回正确内容"],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V2"
        assert any("呼应" in r for r in result.reasons)

    def test_v2_unobservable_acceptance_fails(self) -> None:
        """V-6: acceptance 无可观测动词 → V2 失败。"""
        prd = StructuredPRD(
            goal="提升用户界面的体验",
            scope="做：界面重构；不做：不改后端",
            acceptance_criteria=["用户体验非常好看"],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V2"

    def test_v3_contradiction_fails(self) -> None:
        """V-7: goal=降低延迟 + acceptance=全量扫描 → V3 失败。"""
        prd = StructuredPRD(
            goal="降低接口延迟提升性能",
            scope="做：降低延迟的查询重构；不做：不改对外接口",
            acceptance_criteria=["每次请求触发全量扫描并返回数据"],
        )
        result = validate_prd(prd)
        assert result.passed is False
        assert result.failed_layer == "V3"
        assert any("全量扫描" in r for r in result.reasons)

    def test_v8_user_modified_prd_revalidated(self) -> None:
        """V-8: 用户修改后的 PRD 重过校验。"""
        # 用户传 dict（模拟前端 modified_prd）
        prd_dict = {
            "goal": "修复微信支付回调丢失",
            "scope": "做：新增补偿任务；不做：不改回调",
            "acceptance_criteria": ["触发查单后返回结果"],
        }
        result = validate_prd(prd_dict)
        assert result.passed is True


# ---- ClarifierAgent mock 模式 ----

class TestClarifierAgentMock:
    """ClarifierAgent mock 模式（无 LLM，供 CI）。"""

    def test_a1_mock_returns_clarifying(self) -> None:
        """A1: llm=None → 返回模板回复。"""
        agent = ClarifierAgent(llm=None)
        result = asyncio.run(agent.execute(
            AgentInput(task="支付超时了修一下", context={})
        ))
        assert result.status == "ok"
        assert result.result["clarification_status"] == "clarifying"
        assert "mock" in result.result["reply"].lower()

    def test_a1_mock_includes_user_message(self) -> None:
        """mock 回复应包含用户输入。"""
        agent = ClarifierAgent(llm=None)
        result = asyncio.run(agent.execute(
            AgentInput(task="测试需求描述", context={})
        ))
        assert "测试需求描述" in result.result["reply"]

    def test_a3_invalid_json_returns_error(self) -> None:
        """A3: LLM 输出非 JSON → 降级回复。"""
        class MockLLM:
            async def generate(self, req, task_id):
                class R:
                    content = "这不是 JSON 格式"
                return R()

        agent = ClarifierAgent(llm=MockLLM())
        result = asyncio.run(agent.execute(
            AgentInput(task="测试", context={})
        ))
        assert result.status == "error"
        assert result.result["clarification_status"] == "clarifying"

    def test_a2_valid_json_returns_ok(self) -> None:
        """A2: LLM 输出合法 JSON → 成功解析。"""
        class MockLLM:
            async def generate(self, req, task_id):
                class R:
                    content = """{"reply": "确认需求", "clarification_status": "clarifying", "structured_prd": {"goal": "", "scope": "", "acceptance_criteria": [], "edge_cases": [], "constraints": [], "acceptance_options": []}, "missing_fields": ["goal"]}"""
                return R()

        agent = ClarifierAgent(llm=MockLLM())
        result = asyncio.run(agent.execute(
            AgentInput(task="测试", context={})
        ))
        assert result.status == "ok"
        assert result.result["clarification_status"] == "clarifying"
