# -*- coding: utf-8 -*-
"""RouterAgent chaos tests: fault injection and degradation verification."""

from __future__ import annotations

import pytest

from orbit.router.agent import ModelTier, RouterAgent
from orbit.router.cc_switch import parse_cc_switch
from orbit.router.resolver import AgentModelResolver


class TestCCSwitchChaos:
    """CC_SWITCH parser chaos inputs."""

    def test_very_long_input(self):
        long_input = ",".join([f"Agent{i}:model-{i}" for i in range(100)])
        config = parse_cc_switch(long_input)
        assert len(config.entries) == 100

    def test_special_characters_in_model(self):
        weird = "Dev:deepseek/deepseek-v4-pro-v1.2.3-beta.4"
        config = parse_cc_switch(weird)
        assert len(config.entries) == 1
        assert config.entries[0].model == "deepseek/deepseek-v4-pro-v1.2.3-beta.4"

    def test_unicode_agent_name(self):
        config = parse_cc_switch("TestAgent:model,DeveloperAgent:glm-5.2")
        valid = [e for e in config.entries if e.agent_name == "DeveloperAgent"]
        assert len(valid) == 1

    def test_empty_segments(self):
        config = parse_cc_switch(",,DeveloperAgent:glm-5.2,,")
        assert len(config.entries) == 1

    def test_whitespace_handling(self):
        config = parse_cc_switch("  DeveloperAgent  :  glm-5.2  ")
        assert len(config.entries) == 1
        assert config.entries[0].agent_name == "DeveloperAgent"
        assert config.entries[0].model == "glm-5.2"


class TestRouterAgentChaos:
    """RouterAgent extreme inputs."""

    @pytest.mark.asyncio
    async def test_zero_file_count(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=0, change_type="single_file", risk="low",
            agent_role="developer",
        )
        assert decision.tier in ModelTier

    @pytest.mark.asyncio
    async def test_negative_file_count(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=-5, change_type="config", risk="low",
            agent_role="config_manager",
        )
        assert decision.tier in ModelTier

    @pytest.mark.asyncio
    async def test_unknown_change_type(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=1, change_type="this_type_does_not_exist",
            risk="low", agent_role="developer",
        )
        assert decision.tier in ModelTier

    @pytest.mark.asyncio
    async def test_unknown_risk_level(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=3, change_type="multi_file",
            risk="unknown_risk", agent_role="developer",
        )
        assert decision.tier in ModelTier

    @pytest.mark.asyncio
    async def test_unknown_agent_role(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=1, change_type="single_file", risk="low",
            agent_role="super_ai_overlord",
        )
        assert decision.tier in ModelTier

    @pytest.mark.asyncio
    async def test_very_large_file_count(self):
        agent = RouterAgent()
        decision = await agent.evaluate(
            file_count=99999, change_type="multi_module", risk="high",
            agent_role="architect",
        )
        assert decision.tier == ModelTier.TIER_3


class TestResolverChaos:
    """Resolver degradation tests."""

    @pytest.mark.asyncio
    async def test_resolver_returns_default_when_no_config(self):
        resolver = AgentModelResolver()
        resolved = await resolver.resolve("AnyAgent", None)
        assert resolved.source == "default"
        assert len(resolved.model) > 0

    @pytest.mark.asyncio
    async def test_resolver_handles_empty_agent_name(self):
        resolver = AgentModelResolver()
        resolved = await resolver.resolve("", None)
        assert resolved.source == "default"
