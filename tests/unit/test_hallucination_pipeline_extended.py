"""hallucination/pipeline.py unit tests — pipeline init, _get_validator, edge cases.
Coverage sprint B2-3: 79% → >=88%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.hallucination.pipeline import (
    HallucinationPipeline,
    _FATAL_LEVELS,
    _VALIDATION_ORDER,
)
from orbit.hallucination.schemas import HallucinationLevel


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def pipeline_no_deps():
    """Pipeline with no graph/sandbox — dependency-free layers only."""
    return HallucinationPipeline()


@pytest.fixture
def pipeline_with_graph():
    """Pipeline with mock graph."""
    return HallucinationPipeline(graph=MagicMock())


@pytest.fixture
def pipeline_with_sandbox():
    """Pipeline with mock sandbox."""
    return HallucinationPipeline(sandbox=MagicMock())


# ── Module constants ──────────────────────────────────────


class TestConstants:
    def test_validation_order_has_8_levels(self):
        assert len(_VALIDATION_ORDER) == 8

    def test_fatal_levels(self):
        """L1_GRAPH and L7_RUNTIME are fatal."""
        assert HallucinationLevel.L1_GRAPH in _FATAL_LEVELS
        assert HallucinationLevel.L7_RUNTIME in _FATAL_LEVELS


# ── __init__ ──────────────────────────────────────────────


class TestPipelineInit:
    def test_no_deps(self):
        p = HallucinationPipeline()
        assert p._graph is None
        assert p._sandbox is None

    def test_with_graph(self):
        g = MagicMock()
        p = HallucinationPipeline(graph=g)
        assert p._graph is g

    def test_with_sandbox(self):
        s = MagicMock()
        p = HallucinationPipeline(sandbox=s)
        assert p._sandbox is s

    def test_all_validators_start_none(self):
        p = HallucinationPipeline()
        assert p._l1 is None
        assert p._l2 is None
        assert p._l3 is None
        assert p._l4 is None
        assert p._l5 is None
        assert p._l6 is None
        assert p._l7 is None
        assert p._l8 is None


# ── _get_validator ────────────────────────────────────────


class TestGetValidator:
    """Test _get_validator() — lazy init + dependency checks."""

    def test_l1_graph_no_deps(self, pipeline_no_deps):
        """L1 without graph → None (dependency missing)."""
        result = pipeline_no_deps._get_validator(HallucinationLevel.L1_GRAPH)
        assert result is None

    def test_l1_graph_with_deps(self, pipeline_with_graph):
        """L1 with graph → creates L1GraphValidator."""
        with patch("orbit.hallucination.pipeline.L1GraphValidator") as MockL1:
            result = pipeline_with_graph._get_validator(HallucinationLevel.L1_GRAPH)
            assert result is not None
            MockL1.assert_called_once()

    def test_l1_graph_cached(self, pipeline_with_graph):
        """Second call returns cached instance."""
        with patch("orbit.hallucination.pipeline.L1GraphValidator"):
            v1 = pipeline_with_graph._get_validator(HallucinationLevel.L1_GRAPH)
            v2 = pipeline_with_graph._get_validator(HallucinationLevel.L1_GRAPH)
            assert v1 is v2

    def test_l2_dynamic_no_sandbox(self, pipeline_no_deps):
        """L2 without sandbox → None."""
        result = pipeline_no_deps._get_validator(HallucinationLevel.L2_DYNAMIC)
        assert result is None

    def test_l2_dynamic_with_sandbox(self, pipeline_with_sandbox):
        """L2 with sandbox → creates L2DynamicTracer."""
        with patch("orbit.hallucination.pipeline.L2DynamicTracer") as MockL2:
            result = pipeline_with_sandbox._get_validator(HallucinationLevel.L2_DYNAMIC)
            assert result is not None
            MockL2.assert_called_once()

    def test_l3_entropy_no_deps(self, pipeline_no_deps):
        """L3 never needs external deps."""
        with patch("orbit.hallucination.pipeline.L3EntropyMonitor") as MockL3:
            result = pipeline_no_deps._get_validator(HallucinationLevel.L3_ENTROPY)
            assert result is not None
            MockL3.assert_called_once()

    def test_l4_type_no_deps(self, pipeline_no_deps):
        """L4 never needs external deps."""
        with patch("orbit.hallucination.pipeline.L4TypeValidator") as MockL4:
            result = pipeline_no_deps._get_validator(HallucinationLevel.L4_TYPE)
            assert result is not None

    def test_l5_z3_no_deps(self, pipeline_no_deps):
        """L5 (Z3) is self-contained."""
        with patch("orbit.hallucination.pipeline.L5Z3Validator") as MockL5:
            result = pipeline_no_deps._get_validator(HallucinationLevel.L5_Z3)
            assert result is not None

    def test_l6_contract_no_deps(self, pipeline_no_deps):
        """L6 never needs external deps."""
        with patch("orbit.hallucination.pipeline.L6ContractValidator") as MockL6:
            result = pipeline_no_deps._get_validator(HallucinationLevel.L6_CONTRACT)
            assert result is not None

    def test_l7_runtime_no_sandbox(self, pipeline_no_deps):
        """L7 without sandbox → None."""
        result = pipeline_no_deps._get_validator(HallucinationLevel.L7_RUNTIME)
        assert result is None

    def test_l7_runtime_with_sandbox(self, pipeline_with_sandbox):
        """L7 with sandbox → creates L7RuntimeValidator."""
        with patch("orbit.hallucination.pipeline.L7RuntimeValidator") as MockL7:
            result = pipeline_with_sandbox._get_validator(HallucinationLevel.L7_RUNTIME)
            assert result is not None

    def test_l8_config_no_deps(self, pipeline_no_deps):
        """L8 never needs external deps."""
        with patch("orbit.hallucination.pipeline.L8ConfigValidator") as MockL8:
            result = pipeline_no_deps._get_validator(HallucinationLevel.L8_CONFIG)
            assert result is not None


# ── validate methods ──────────────────────────────────────


class TestValidateMethods:
    """Test validate_quick, validate_full, validate."""

    @pytest.mark.asyncio
    async def test_validate_quick(self, pipeline_no_deps):
        """Quick validation runs L1+L4+L3."""
        with patch("orbit.hallucination.pipeline.TraceCollector"):
            with patch.object(pipeline_no_deps, "_run_levels") as mock_run:
                await pipeline_no_deps.validate_quick("code")
                mock_run.assert_called_once()
                levels = mock_run.call_args[0][1]
                assert HallucinationLevel.L1_GRAPH in levels
                assert HallucinationLevel.L4_TYPE in levels
                assert HallucinationLevel.L3_ENTROPY in levels

    @pytest.mark.asyncio
    async def test_validate_full(self, pipeline_no_deps):
        """Full validation runs all L1-L8."""
        with patch("orbit.hallucination.pipeline.TraceCollector"):
            with patch.object(pipeline_no_deps, "_run_levels") as mock_run:
                await pipeline_no_deps.validate_full("code")
                mock_run.assert_called_once()
                levels = mock_run.call_args[0][1]
                assert len(levels) == 8

    @pytest.mark.asyncio
    async def test_validate_max_level(self, pipeline_no_deps):
        """validate(max_level=L4) → only L1+L4+L3."""
        with patch.object(pipeline_no_deps, "_run_levels") as mock_run:
            await pipeline_no_deps.validate("code", max_level=HallucinationLevel.L4_TYPE)
            levels = mock_run.call_args[0][1]
            for l in levels:
                assert l <= HallucinationLevel.L4_TYPE

    @pytest.mark.asyncio
    async def test_validate_no_max(self, pipeline_no_deps):
        """validate(max_level=None) → full."""
        with patch.object(pipeline_no_deps, "_run_levels") as mock_run:
            await pipeline_no_deps.validate("code")
            levels = mock_run.call_args[0][1]
            assert len(levels) == 8
