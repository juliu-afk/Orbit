"""RouterAgent + AgentModelResolver + CC_SWITCH 单元测试。

覆盖 AC1-AC3, AC8.
"""

from __future__ import annotations

import pytest

from orbit.router.agent import (
    TIER_MODEL_MAP,
    ModelTier,
    RouterAgent,
    RouterDecision,
)
from orbit.router.cc_switch import parse_cc_switch
from orbit.router.resolver import AgentModelResolver
from orbit.router.weights import ScoreWeights

# ============================================================
# RouterAgent 测试 (AC1)
# ============================================================


class TestRouterAgent:
    """AC1: RouterAgent 根据任务复杂度输出 ModelTier。"""

    @pytest.mark.asyncio
    async def test_simple_task_returns_tier1(self):
        """简单任务 → Tier 1（DS Flash）。"""
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=1,
            change_type="single_function",
            risk="low",
            agent_role="developer",
        )
        assert decision.tier == ModelTier.TIER_1
        assert decision.confidence > 0.5

    @pytest.mark.asyncio
    async def test_complex_task_returns_tier3(self):
        """复杂任务（多文件+架构）→ Tier 3（DS V4 Pro）。"""
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=10,
            change_type="multi_module",
            risk="medium",
            agent_role="architect",
        )
        assert decision.tier == ModelTier.TIER_3
        assert decision.confidence > 0.7

    @pytest.mark.asyncio
    async def test_config_change_returns_tier0(self):
        """纯配置修改 → Tier 0（本地规则引擎）。"""
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=1,
            change_type="config",
            risk="low",
            agent_role="config_manager",
        )
        assert decision.tier == ModelTier.TIER_0

    @pytest.mark.asyncio
    async def test_high_risk_forces_higher_tier(self):
        """高风险任务（安全/并发）→ 推高 Tier。"""
        agent = RouterAgent()
        # 中等复杂度但高风险 → 至少 Tier 2+
        decision = await agent.evaluate(
            file_count=3,
            change_type="multi_file",
            risk="high",
            agent_role="developer",
        )
        assert decision.tier in (ModelTier.TIER_2, ModelTier.TIER_3)

    @pytest.mark.asyncio
    async def test_historical_similar_downgrades(self):
        """有历史成功先例 → 降级（更低的 Tier）。"""
        agent = RouterAgent()
        without_history = await agent.evaluate(
            file_count=3,
            change_type="multi_file",
            risk="low",
            agent_role="developer",
            has_similar_history=False,
        )
        with_history = await agent.evaluate(
            file_count=3,
            change_type="multi_file",
            risk="low",
            agent_role="developer",
            has_similar_history=True,
        )
        # 有历史先例应该不高于无历史的 Tier
        tier_order = ["tier_0", "tier_1", "tier_2", "tier_3"]
        assert tier_order.index(with_history.tier.value) <= tier_order.index(
            without_history.tier.value
        )

    @pytest.mark.asyncio
    async def test_score_clamped_to_0_100(self):
        """评分钳制到 [0, 100] 范围。"""
        agent = RouterAgent()
        # 极端低分场景
        low = await agent.evaluate(
            file_count=1,
            change_type="config",
            risk="low",
            agent_role="config_manager",
            has_similar_history=True,
        )
        assert 0 <= low.confidence <= 1.0

        # 极端高分场景
        high = await agent.evaluate(
            file_count=20,
            change_type="multi_module",
            risk="high",
            agent_role="architect",
            has_similar_history=False,
        )
        assert high.tier == ModelTier.TIER_3

    @pytest.mark.asyncio
    async def test_custom_weights_from_env(self, monkeypatch):
        """环境变量覆盖默认权重。"""
        monkeypatch.setenv("ROUTER_WEIGHT_FILES", "50")
        monkeypatch.setenv("ROUTER_WEIGHT_RISK", "10")

        agent = RouterAgent(weights=ScoreWeights.from_env())
        assert agent.weights.files == 50
        assert agent.weights.risk == 10

    @pytest.mark.asyncio
    async def test_fallback_tier_is_lower(self):
        """降级 Tier 比当前 Tier 低一级。"""
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=3,
            change_type="multi_file",
            risk="medium",
            agent_role="developer",
        )
        # Tier 2 的 fallback 应该是 Tier 1
        if decision.tier == ModelTier.TIER_2:
            assert decision.fallback_tier == ModelTier.TIER_1
        elif decision.tier == ModelTier.TIER_3:
            assert decision.fallback_tier == ModelTier.TIER_2

    @pytest.mark.asyncio
    async def test_tier0_has_no_fallback(self):
        """Tier 0 没有降级 Tier。"""
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=1,
            change_type="config",
            risk="low",
            agent_role="config_manager",
        )
        if decision.tier == ModelTier.TIER_0:
            assert decision.fallback_tier is None


# ============================================================
# AgentModelResolver 测试 (AC2)
# ============================================================


class TestAgentModelResolver:
    """AC2: AgentModelResolver 按优先级正确解析模型。"""

    @pytest.mark.asyncio
    async def test_cc_switch_force_has_highest_priority(self, monkeypatch):
        """CC_SWITCH force 模式 → 最高优先级，覆盖一切。"""
        monkeypatch.setenv("CC_SWITCH", "DeveloperAgent:deepseek/deepseek-v4-pro,force")
        monkeypatch.setenv("AGENT_DEVELOPERAGENT_MODEL", "openai/glm-5.2")

        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_1, reason="test", confidence=0.8)
        resolved = await resolver.resolve("DeveloperAgent", decision)

        assert resolved.model == "deepseek/deepseek-v4-pro"
        assert resolved.source == "cc_switch_force"
        assert resolved.is_forced

    @pytest.mark.asyncio
    async def test_env_var_overrides_cc_switch_no_force(self, monkeypatch):
        """环境变量 → 高于 CC_SWITCH no-force。"""
        monkeypatch.setenv("CC_SWITCH", "DeveloperAgent:openai/glm-5.2,no-force")
        monkeypatch.setenv("AGENT_DEVELOPERAGENT_MODEL", "deepseek/deepseek-v4-flash")

        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_1, reason="test", confidence=0.8)
        resolved = await resolver.resolve("DeveloperAgent", decision)

        assert resolved.model == "deepseek/deepseek-v4-flash"
        assert resolved.source == "environment"

    @pytest.mark.asyncio
    async def test_router_used_when_no_config(self):
        """无 CC_SWITCH 无环境变量 → 使用 RouterAgent 推荐。"""
        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_2, reason="中等复杂度", confidence=0.85)
        resolved = await resolver.resolve("DeveloperAgent", decision)

        assert resolved.source == "router"
        assert resolved.model == TIER_MODEL_MAP[ModelTier.TIER_2.value]

    @pytest.mark.asyncio
    async def test_default_model_as_last_resort(self, monkeypatch):
        """无 RouterAgent 推荐 + 无配置 → 使用系统默认。"""
        monkeypatch.delenv("CC_SWITCH", raising=False)

        resolver = AgentModelResolver()
        resolved = await resolver.resolve("UnknownAgent", None)

        assert resolved.source == "default"
        # 默认模型存在
        assert len(resolved.model) > 0

    @pytest.mark.asyncio
    async def test_tier0_returns_empty_model(self):
        """Tier 0（本地规则引擎）→ 空模型（不调 LLM）。"""
        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_0, reason="极简", confidence=0.95)
        resolved = await resolver.resolve("ConfigAgent", decision)

        assert resolved.model == ""
        assert resolved.tier == ModelTier.TIER_0
        assert resolved.source == "router"

    @pytest.mark.asyncio
    async def test_cc_switch_all_applies_to_any_agent(self, monkeypatch):
        """CC_SWITCH all: → 对所有 Agent 生效。"""
        monkeypatch.setenv("CC_SWITCH", "all:openai/glm-5.2")

        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_3, reason="test", confidence=0.9)

        # 两个不同 Agent 都应该命中 all:
        r1 = await resolver.resolve("DeveloperAgent", decision)
        r2 = await resolver.resolve("ArchitectAgent", decision)

        assert r1.model == "openai/glm-5.2"
        assert r2.model == "openai/glm-5.2"
        assert r1.source == "cc_switch"
        assert r2.source == "cc_switch"

    @pytest.mark.asyncio
    async def test_env_var_case_insensitive(self, monkeypatch):
        """AGENT_*_MODEL 环境变量大小写不敏感。"""
        monkeypatch.setenv("AGENT_DEVELOPERAGENT_MODEL", "openai/glm-5.2")

        resolver = AgentModelResolver()
        resolved = await resolver.resolve("DeveloperAgent", None)

        assert resolved.model == "openai/glm-5.2"
        assert resolved.source == "environment"

    @pytest.mark.asyncio
    async def test_cache_stores_result(self):
        """resolver 缓存解析结果。"""
        resolver = AgentModelResolver()
        decision = RouterDecision(tier=ModelTier.TIER_2, reason="test", confidence=0.8)
        await resolver.resolve("DeveloperAgent", decision)

        cached = resolver.get_cached("DeveloperAgent")
        assert cached is not None
        assert cached.source == "router"


# ============================================================
# CC_SWITCH 解析器测试 (AC3)
# ============================================================


class TestCCSwitchParser:
    """AC3: CC_SWITCH 格式解析。"""

    def test_all_mode(self):
        config = parse_cc_switch("all:deepseek-v3")
        assert len(config.entries) == 1
        assert config.entries[0].agent_name == "all"
        assert config.entries[0].model == "deepseek-v3"
        assert config.entries[0].mode == "no-force"  # 默认

    def test_per_agent_force_mode(self):
        config = parse_cc_switch("DeveloperAgent:glm-5.2,force")
        assert len(config.entries) == 1
        assert config.entries[0].agent_name == "DeveloperAgent"
        assert config.entries[0].model == "glm-5.2"
        assert config.entries[0].mode == "force"
        assert config.entries[0].is_force

    def test_multi_agent(self):
        config = parse_cc_switch("DeveloperAgent:glm-5.2,ArchitectAgent:deepseek-v3")
        assert len(config.entries) == 2
        assert config.entries[0].agent_name == "DeveloperAgent"
        assert config.entries[1].agent_name == "ArchitectAgent"

    def test_no_force_mode(self):
        config = parse_cc_switch("DeveloperAgent:glm-5.2,no-force")
        assert config.entries[0].mode == "no-force"
        assert not config.entries[0].is_force

    def test_empty_cc_switch(self):
        config = parse_cc_switch("")
        assert len(config.entries) == 0

    def test_none_cc_switch(self):
        config = parse_cc_switch(None)
        assert len(config.entries) == 0

    def test_invalid_format_skipped(self, monkeypatch):
        """格式错误 → 跳过该条目，不抛异常。"""
        monkeypatch.setenv("CC_SWITCH", "badformat,DeveloperAgent:glm-5.2")
        config = parse_cc_switch()
        # badformat 被跳过，DeveloperAgent 被正常解析
        assert len(config.entries) == 1
        assert config.entries[0].agent_name == "DeveloperAgent"

    def test_invalid_segment_no_colon(self):
        """没有冒号的片段 → 跳过。"""
        config = parse_cc_switch("invalid-entry")
        assert len(config.entries) == 0

    def test_cc_switch_from_env(self, monkeypatch):
        """从环境变量自动读取。"""
        monkeypatch.setenv("CC_SWITCH", "all:deepseek-v3,force")
        config = parse_cc_switch()
        assert config.entries[0].model == "deepseek-v3"
        assert config.entries[0].is_force
