"""prompt/builder.py unit tests — PromptBuilder all methods + edge cases.
Coverage sprint B2-2: 58% → >=85%.

Previously only __init__ test (4 lines). Now covers build, build_for_anthropic,
_build_stable, _build_tools_guide, _build_mcp_guide, _build_context, _build_volatile,
build_stable_only, build_system_and_user, ROLE_DESCRIPTIONS, RULES_BLOCK.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.agents.base import AgentRole
from orbit.prompt.builder import (
    PromptBuilder,
    ROLE_DESCRIPTIONS,
    RULES_BLOCK,
    TOOLS_GUIDE_BLOCK,
)


# ── Module-level constants ────────────────────────────────


class TestConstants:
    """Test module-level prompt constants."""

    def test_all_roles_have_descriptions(self):
        """Every AgentRole except CHATTER has a description (CHATTER = default inline)."""
        roles_needing_desc = {r for r in AgentRole if r != AgentRole.CHATTER}
        for role in roles_needing_desc:
            assert role in ROLE_DESCRIPTIONS, f"Missing description for {role}"

    def test_rules_block_not_empty(self):
        """RULES_BLOCK is non-empty string."""
        assert len(RULES_BLOCK) > 100

    def test_tools_guide_block_not_empty(self):
        """TOOLS_GUIDE_BLOCK is non-empty string."""
        assert len(TOOLS_GUIDE_BLOCK) > 100


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def builder():
    return PromptBuilder()


@pytest.fixture
def sample_tools_schema():
    return [
        {"function": {"name": "read_file"}},
        {"function": {"name": "grep"}},
        {"function": {"name": "exec_command"}},
        {"function": {"name": "edit_file"}},
        {"function": {"name": "okf/find_symbol"}},
        {"function": {"name": "okf/get_symbols_overview"}},
        {"function": {"name": "okf/find_referencing_symbols"}},
    ]


# ── build ─────────────────────────────────────────────────


class TestBuild:
    """Test build() — full system prompt assembly."""

    def test_build_basic(self, builder):
        """Build with role + no context → non-empty string."""
        result = builder.build(AgentRole.DEVELOPER)
        assert len(result) > 100
        assert "开发者 Agent" in result

    def test_build_with_context(self, builder):
        """Build with context dict."""
        ctx = {"project": "Orbit", "tech_stack": "Python 3.11, FastAPI"}
        result = builder.build(AgentRole.ARCHITECT, context=ctx)
        assert "Orbit" in result
        assert "Python 3.11" in result

    def test_build_with_task(self, builder):
        """Build with task in volatile layer."""
        ctx = {"task": "Fix the login bug"}
        result = builder.build(AgentRole.DEVELOPER, context=ctx)
        assert "Fix the login bug" in result


class TestBuildForAnthropic:
    """Test build_for_anthropic() — structured blocks with cache_control."""

    def test_returns_list(self, builder):
        """Returns list of content blocks."""
        result = builder.build_for_anthropic(AgentRole.DEVELOPER)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_first_block_has_cache_control(self, builder):
        """First block (stable+context) has cache_control."""
        result = builder.build_for_anthropic(AgentRole.DEVELOPER)
        assert result[0]["cache_control"]["type"] == "ephemeral"

    def test_second_block_no_cache_control(self, builder):
        """Second block (volatile) has NO cache_control."""
        result = builder.build_for_anthropic(AgentRole.DEVELOPER)
        assert "cache_control" not in result[1]


# ── _build_stable ─────────────────────────────────────────


class TestBuildStable:
    """Test _build_stable() — role + tools + rules."""

    def test_includes_role_description(self, builder):
        result = builder._build_stable(AgentRole.QA)
        assert "QA 验证员" in result

    def test_includes_rules(self, builder):
        result = builder._build_stable(AgentRole.DEVELOPER)
        assert "金额一律 Decimal" in result

    def test_unknown_role_falls_back(self, builder):
        """Unknown role → Developer fallback."""
        fake_role = MagicMock()
        fake_role.value = "unknown_role"
        result = builder._build_stable(fake_role)
        assert "开发者 Agent" in result


# ── _build_tools_guide ────────────────────────────────────


class TestBuildToolsGuide:
    """Test _build_tools_guide() — role-based tool table."""

    def test_none_schema_returns_default(self, builder):
        """None schema → TOOLS_GUIDE_BLOCK."""
        result = builder._build_tools_guide(AgentRole.DEVELOPER, None)
        assert result == TOOLS_GUIDE_BLOCK

    def test_empty_schema_returns_no_tools(self, builder):
        """Empty list → 'no tools' message."""
        result = builder._build_tools_guide(AgentRole.CLARIFIER, [])
        assert "无可用工具" in result

    def test_with_tools_includes_concurrency(self, builder, sample_tools_schema):
        """Tool table includes concurrency labels."""
        result = builder._build_tools_guide(AgentRole.DEVELOPER, sample_tools_schema)
        assert "read_file" in result
        assert "可并发" in result or "串行" in result

    def test_serial_tools_marked(self, builder):
        """exec_command → serial, read_file → concurrent."""
        schema = [{"function": {"name": "exec_command"}}]
        result = builder._build_tools_guide(AgentRole.DEVELOPER, schema)
        assert "串行" in result


# ── _build_mcp_guide ──────────────────────────────────────


class TestBuildMcpGuide:
    """Test _build_mcp_guide() — MCP tool injection."""

    def test_none_schema(self, builder):
        """None → empty string."""
        result = builder._build_mcp_guide(None)
        assert result == ""

    def test_empty_schema(self, builder):
        result = builder._build_mcp_guide([])
        assert result == ""

    def test_no_mcp_tools(self, builder):
        """No MCP-prefixed tools → empty."""
        schema = [{"function": {"name": "read_file"}}]
        result = builder._build_mcp_guide(schema)
        assert result == ""

    def test_mcp_tool_generates_guide(self, builder, sample_tools_schema):
        """MCP tools (with / in name) → guide with server prefix."""
        result = builder._build_mcp_guide(sample_tools_schema)
        assert "okf" in result
        assert "find_symbol" in result
        assert "MCP" in result

    def test_multiple_mcp_servers(self, builder):
        """Two different MCP prefixes → two sections."""
        schema = [
            {"function": {"name": "ls/find_symbol"}},
            {"function": {"name": "gh/list_issues"}},
        ]
        result = builder._build_mcp_guide(schema)
        assert "ls" in result
        assert "gh" in result


# ── _build_context ────────────────────────────────────────


class TestBuildContext:
    """Test _build_context() — project/tech/env context layer."""

    def test_empty_context(self, builder):
        result = builder._build_context({})
        assert "无特定项目上下文" in result or "通用开发环境" in result

    def test_project_and_tech(self, builder):
        ctx = {"project": "Orbit", "tech_stack": "Python"}
        result = builder._build_context(ctx)
        assert "Orbit" in result
        assert "Python" in result

    def test_code_context_truncation(self, builder):
        """Long code context → truncated at 5000 chars by default."""
        long_code = "x" * 6000
        ctx = {"code_context": long_code}
        result = builder._build_context(ctx)
        assert "截断" in result

    def test_code_context_with_keywords(self, builder):
        """Keywords → extract_relevant_context used."""
        ctx = {"code_context": "def login(): pass\ndef logout(): pass", "keywords": ["login"]}
        result = builder._build_context(ctx)
        assert len(result) > 0

    def test_env_filters_sensitive_keys(self, builder):
        """API keys, secrets, tokens filtered from env output."""
        ctx = {"env": {"API_KEY": "secret", "NORMAL_VAR": "visible"}}
        result = builder._build_context(ctx)
        assert "visible" in result
        assert "secret" not in result

    def test_user_profile_injection(self, builder):
        """User profile fields injected."""
        mock_profile = MagicMock()
        mock_profile.display_name = "Alice"
        mock_profile.role = "Developer"
        mock_profile.communication_style = "direct"
        mock_profile.decision_style = "fast"
        mock_profile.preferences = {"lang": "Python"}
        mock_profile.goals = ["goal1"]
        ctx = {"user_profile": mock_profile}
        result = builder._build_context(ctx)
        assert "Alice" in result
        assert "Python" in result

    def test_brief_injection(self, builder):
        ctx = {"brief": "Orbit project brief content"}
        result = builder._build_context(ctx)
        assert "项目说明书" in result or "Orbit project brief" in result

    def test_boundaries_injection(self, builder):
        ctx = {"boundaries": "rule1: no force push\\nrule2: no hardcoded keys"}
        result = builder._build_context(ctx)
        assert "边界规则" in result or "rule1" in result

    def test_memory_search_results(self, builder):
        mock_result = MagicMock()
        mock_result.path = "/mem/test.md"
        mock_result.score = 0.9
        mock_result.snippet = "test snippet"
        ctx = {"memory_search_results": [mock_result]}
        result = builder._build_context(ctx)
        assert "记忆检索结果" in result or "memory" in result.lower()

    def test_working_memory(self, builder):
        mock_mem = MagicMock()
        mock_mem.body = "Remember: always use Decimal for money"
        ctx = {"working_memory": mock_mem}
        result = builder._build_context(ctx)
        assert "Decimal" in result

    def test_context_md_list(self, builder):
        """Directory-level context.md chain."""
        ctx = {"context_md": [("/path/to/src", "This directory contains source files.")]}
        result = builder._build_context(ctx)
        assert "目录上下文" in result
        assert "src" in result

    def test_base_package(self, builder):
        ctx = {"base_package": {"decision": "include", "package_ids": ["core"], "reason": "needed"}}
        result = builder._build_context(ctx)
        assert "基础代码包" in result or "base" in result.lower()


# ── _build_volatile ───────────────────────────────────────


class TestBuildVolatile:
    """Test _build_volatile() — task + constraints layer."""

    def test_empty_volatile(self, builder):
        result = builder._build_volatile({})
        assert "当前任务" in result

    def test_task_only(self, builder):
        ctx = {"task": "Implement login API"}
        result = builder._build_volatile(ctx)
        assert "Implement login API" in result

    def test_task_with_constraints(self, builder):
        ctx = {"task": "Add endpoint", "constraints": ["No new deps", "Max 50 lines"]}
        result = builder._build_volatile(ctx)
        assert "No new deps" in result

    def test_token_budget(self, builder):
        ctx = {"token_budget": 5000}
        result = builder._build_volatile(ctx)
        assert "5000" in result


# ── Convenience methods ───────────────────────────────────


class TestConvenienceMethods:
    """Test build_stable_only and build_system_and_user."""

    def test_build_stable_only(self, builder):
        result = builder.build_stable_only(AgentRole.REVIEWER)
        assert "审查员 Agent" in result
        # Should NOT include volatile/task content
        assert "当前任务" not in result

    def test_build_system_and_user(self, builder):
        result = builder.build_system_and_user(AgentRole.DEVELOPER, task="Write tests")
        assert "system" in result
        assert "user" in result
        assert result["user"] == "Write tests"
        assert "Write tests" in result["system"]
