"""Branch coverage sprint — parameterized boundary tests.
Strategy C: target modules at 80%+ line but <70% branch coverage.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.agents.base import AgentRole
from orbit.hallucination.pipeline import HallucinationPipeline
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult
from orbit.tools.registry.core import _path_to_module


# ── _path_to_module branches ──────────────────────────────


class TestPathToModuleBranches:
    def test_src_orbit_nested(self):
        assert _path_to_module("src/orbit/a/b/c.py") == "orbit.a.b.c"

    def test_orbit_no_src(self):
        assert _path_to_module("orbit/svc/calc.py") == "orbit.svc.calc"

    def test_no_orbit_no_src(self):
        assert _path_to_module("/unknown/path/tool.py") == "orbit.tools.tool"

    def test_empty_parts(self):
        result = _path_to_module("tool.py")
        assert "orbit.tools.tool" in result


# ── HallucinationPipeline branches ────────────────────────


class TestHallucinationPipelineBranches:
    @pytest.fixture
    def pipeline(self):
        return HallucinationPipeline()

    @pytest.mark.asyncio
    async def test_run_levels_empty(self, pipeline):
        result = await pipeline._run_levels("code", [], stop_on_first_error=False)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_levels_with_ablation(self, pipeline):
        with patch("orbit.effectiveness.ablation.AblationContext.is_disabled", return_value=True):
            result = await pipeline._run_levels("code", [HallucinationLevel.L3_ENTROPY], stop_on_first_error=False)
            assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_run_levels_missing_dependency(self, pipeline):
        result = await pipeline._run_levels("code", [HallucinationLevel.L1_GRAPH], stop_on_first_error=False)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_levels_fatal_stops(self, pipeline):
        """Fatal level failure stops pipeline."""
        async def mock_validate(code):
            return ValidationResult(passed=False, level=HallucinationLevel.L1_GRAPH, errors=["fatal"], warnings=[])

        mock_val = MagicMock()
        mock_val.validate = mock_validate

        with patch.object(pipeline, "_get_validator", return_value=mock_val):
            result = await pipeline._run_levels(
                "code", [HallucinationLevel.L1_GRAPH, HallucinationLevel.L3_ENTROPY],
                stop_on_first_error=False,
            )
            assert result.passed is False


# ── ValidationResult edge cases ───────────────────────────


class TestValidationResultBranches:
    def test_passed(self):
        r = ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH, errors=[], warnings=[])
        assert r.passed

    def test_failed_with_errors(self):
        r = ValidationResult(passed=False, level=HallucinationLevel.L5_Z3, errors=["e1", "e2"], warnings=["w1"])
        assert not r.passed
        assert len(r.errors) == 2
        assert len(r.warnings) == 1


# ── AgentRole exhaustive ──────────────────────────────────


class TestAgentRoleBranches:
    def test_all_roles(self):
        roles = list(AgentRole)
        assert len(roles) >= 7

    def test_each_role_has_value(self):
        for role in AgentRole:
            assert len(role.value) > 0
