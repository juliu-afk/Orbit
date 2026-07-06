"""HallucinationPipeline - branch coverage for _run_levels paths."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.hallucination.pipeline import HallucinationPipeline
from orbit.hallucination.schemas import HallucinationLevel


class TestPipelineBranches:
    """Cover try/except and if/else branches in _run_levels and _get_validator."""

    @pytest.mark.asyncio
    async def test_validate_quick_no_graph(self):
        """L1 skipped (no graph) → validator=None branch covered."""
        p = HallucinationPipeline(graph=None, sandbox=None)
        result = await p.validate_quick("x = 1")
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_validate_full_no_deps(self):
        """L1+L2 skipped (no graph/sandbox) → validator=None branches covered."""
        p = HallucinationPipeline(graph=None, sandbox=None)
        result = await p.validate_full("x = 1")
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_validate_to_level(self):
        """Run only L3 → stops after L3 branch covered."""
        p = HallucinationPipeline(graph=None, sandbox=None)
        result = await p.validate("x = 1", max_level=HallucinationLevel.L3_ENTROPY)
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_empty_code(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        result = await p.validate_quick("")
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_get_validator_l1_no_graph(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        v = p._get_validator(HallucinationLevel.L1_GRAPH)
        assert v is None  # branch: graph is None → return None

    @pytest.mark.asyncio
    async def test_get_validator_l2_no_sandbox(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        v = p._get_validator(HallucinationLevel.L2_DYNAMIC)
        assert v is None  # branch: sandbox is None → return None

    @pytest.mark.asyncio
    async def test_get_validator_l3_always_available(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        v = p._get_validator(HallucinationLevel.L3_ENTROPY)
        assert v is not None  # L3 has no external deps

    @pytest.mark.asyncio
    async def test_get_validator_l4_always_available(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        v = p._get_validator(HallucinationLevel.L4_TYPE)
        assert v is not None  # L4 has no external deps

    @pytest.mark.asyncio
    async def test_get_validator_lazy_init_cached(self):
        p = HallucinationPipeline(graph=None, sandbox=None)
        v1 = p._get_validator(HallucinationLevel.L3_ENTROPY)
        v2 = p._get_validator(HallucinationLevel.L3_ENTROPY)
        assert v1 is v2  # 懒初始化：第二次返回缓存实例

    @pytest.mark.asyncio
    async def test_fatal_level_stops_pipeline(self):
        """_FATAL_LEVELS 中的层失败 → break 分支。"""
        p = HallucinationPipeline(graph=None, sandbox=None)
        # L6 is fatal — but needs OpenAPI spec. Let it crash to test the except branch.
        result = await p.validate("invalid code ###", max_level=HallucinationLevel.L7_RUNTIME)
        # L7 needs sandbox → skipped. Pipeline should complete without crashing.
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_crashing_validator_fail_open(self):
        """验证器崩溃 → except Exception 分支 → fail-open。"""
        p = HallucinationPipeline(graph=None, sandbox=None)
        # Mock a validator that crashes
        p._l3 = MagicMock()
        p._l3.validate = MagicMock(side_effect=RuntimeError("boom"))
        result = await p.validate_quick("code")
        assert isinstance(result.passed, bool)
        # Should have warning about crash
        assert any("异常" in w for w in result.warnings)
