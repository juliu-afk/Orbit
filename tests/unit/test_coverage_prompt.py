"""覆盖率补测——prompt/builder.py (PromptBuilder)."""

from __future__ import annotations

import pytest

from orbit.agents.base import AgentRole
from orbit.prompt.builder import PromptBuilder


class TestPromptBuilder:
    def test_init(self):
        builder = PromptBuilder()
        assert builder is not None

    def test_build_stable_only(self):
        builder = PromptBuilder()
        prompt = builder.build_stable_only(role=AgentRole.DEVELOPER)
        assert len(prompt) > 0

    def test_build_stable_only_all_roles(self):
        builder = PromptBuilder()
        for role in (AgentRole.DEVELOPER, AgentRole.ARCHITECT, AgentRole.REVIEWER, AgentRole.QA):
            prompt = builder.build_stable_only(role=role)
            assert len(prompt) > 0

    def test_build_returns_string(self):
        builder = PromptBuilder()
        result = builder.build(role=AgentRole.DEVELOPER, context={"prd": "auth system"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_for_anthropic(self):
        builder = PromptBuilder()
        result = builder.build_for_anthropic(role=AgentRole.DEVELOPER, context={"prd": "simple app"})
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "cache_control" in result[0]

    def test_build_system_and_user(self):
        builder = PromptBuilder()
        result = builder.build_system_and_user(
            role=AgentRole.DEVELOPER,
            task="add pagination",
            context={"prd": "list view"},
        )
        assert "system" in result
        assert "user" in result
        assert len(result["user"]) > 0

    def test_build_with_tools(self):
        builder = PromptBuilder()
        tools = [{"name": "read_file", "description": "read a file"}]
        result = builder.build(
            role=AgentRole.DEVELOPER,
            context={"prd": "config reader"},
            tools_schema=tools,
        )
        assert isinstance(result, str)

    def test_build_stable_cached(self):
        builder = PromptBuilder()
        p1 = builder.build_stable_only(role=AgentRole.DEVELOPER)
        p2 = builder.build_stable_only(role=AgentRole.DEVELOPER)
        assert p1 == p2  # 缓存

    def test_build_empty_context(self):
        builder = PromptBuilder()
        result = builder.build(role=AgentRole.DEVELOPER)
        assert len(result) > 0
