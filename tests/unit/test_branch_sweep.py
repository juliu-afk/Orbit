"""Branch coverage sweep — parameterized tests for high-brpart modules."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.agents.base import AgentRole
from orbit.hallucination.pipeline import HallucinationPipeline, _VALIDATION_ORDER
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult
from orbit.prompt.builder import PromptBuilder, ROLE_DESCRIPTIONS


class TestPipelineEveryLevel:
    """Test _get_validator for every level in _VALIDATION_ORDER."""

    @pytest.fixture
    def pipeline(self):
        return HallucinationPipeline()

    @pytest.mark.parametrize("level", _VALIDATION_ORDER)
    def test_get_validator_returns_or_none(self, pipeline, level):
        """Each level either returns a validator or None (missing deps)."""
        result = pipeline._get_validator(level)
        # Should return None (missing deps) or a validator object
        assert result is None or hasattr(result, "validate")


class TestPromptBuilderBranches:
    """Branch coverage for PromptBuilder edge cases."""

    @pytest.fixture
    def builder(self):
        return PromptBuilder()

    @pytest.mark.parametrize("role", list(AgentRole))
    def test_build_stable_all_roles(self, builder, role):
        """Every role produces non-empty stable prompt."""
        result = builder._build_stable(role)
        assert len(result) > 0

    def test_build_context_with_keywords_extraction(self, builder):
        """Keywords trigger extract_relevant_context."""
        ctx = {"code_context": "def a(): pass\ndef b(): pass\ndef c(): pass", "keywords": ["a", "b"]}
        result = builder._build_context(ctx)
        assert len(result) > 0

    def test_build_context_without_keywords_truncation(self, builder):
        """No keywords → simple truncation."""
        long_code = "x" * 6000
        ctx = {"code_context": long_code}
        result = builder._build_context(ctx)
        assert "..." in result or "截断" in result

    def test_build_context_env_sensitive_filtered(self, builder):
        """Sensitive env keys are filtered."""
        ctx = {"env": {"API_KEY": "sk-123", "DB_PASSWORD": "pw", "APP_NAME": "orbit", "TOKEN": "xyz"}}
        result = builder._build_context(ctx)
        assert "orbit" in result
        assert "sk-123" not in result

    def test_build_volatile_constraints(self, builder):
        """Multiple constraints are listed."""
        ctx = {"task": "fix bug", "constraints": ["no new deps", "max 20 lines", "must have test"]}
        result = builder._build_volatile(ctx)
        assert "no new deps" in result
        assert "max 20 lines" in result

    def test_build_for_anthropic_with_context(self, builder):
        """build_for_anthropic with rich context."""
        ctx = {"project": "Orbit", "tech_stack": "Python", "task": "test"}
        result = builder.build_for_anthropic(AgentRole.DEVELOPER, context=ctx)
        assert len(result) == 2
        assert result[0]["cache_control"]["type"] == "ephemeral"

    def test_build_for_anthropic_task_in_volatile(self, builder):
        """Task appears in volatile (second) block."""
        ctx = {"task": "Implement feature X"}
        result = builder.build_for_anthropic(AgentRole.DEVELOPER, context=ctx)
        assert "Implement feature X" in result[1]["text"]


class TestValidationResultBranchCoverage:
    """All ValidationResult states."""

    def test_passed_with_warnings(self):
        r = ValidationResult(passed=True, level=HallucinationLevel.L4_TYPE, errors=[], warnings=["w1"])
        assert r.passed
        assert r.warnings

    def test_failed_empty_warnings(self):
        r = ValidationResult(passed=False, level=HallucinationLevel.L5_Z3, errors=["e1"], warnings=[])
        assert not r.passed

    def test_all_valid(self):
        r = ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH, errors=[], warnings=[])
        assert r.passed
        assert not r.errors
        assert not r.warnings
