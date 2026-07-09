"""Goal ensemble 单元测试——覆盖纯函数+集成决策逻辑。"""
from __future__ import annotations

import pytest

from orbit.goal.ensemble import (
    ENSEMBLE_WEIGHT_THRESHOLD,
    FUSION_DELTA_THRESHOLD,
    MAX_ENSEMBLE_CANDIDATES,
    EnsembleResult,
    JudgeScore,
    ModelEnsemble,
)


class TestJudgeScore:
    def test_total_weighted(self):
        s = JudgeScore(correctness=1.0, performance=0.8, maintainability=0.6)
        expected = 1.0 * 0.5 + 0.8 * 0.25 + 0.6 * 0.25
        assert s.total == expected

    def test_total_defaults_zero(self):
        s = JudgeScore()
        assert s.total == 0.0

    def test_total_correctness_dominant(self):
        s1 = JudgeScore(correctness=1.0, performance=0.0, maintainability=0.0)
        s2 = JudgeScore(correctness=0.0, performance=0.6, maintainability=0.6)
        assert s1.total > s2.total


class TestEnsembleResult:
    def test_defaults(self):
        r = EnsembleResult()
        assert r.selected is None
        assert r.method == "selection"

    def test_is_fused(self):
        r = EnsembleResult(method="fusion")
        assert r.is_fused is True

    def test_is_not_fused(self):
        r = EnsembleResult(method="selection")
        assert r.is_fused is False


class _FakeTask:
    def __init__(self, desc):
        self.description = desc
        self.id = "fake-1"


class TestModelEnsemble:
    def test_init(self):
        e = ModelEnsemble()
        assert e is not None

    @pytest.mark.asyncio
    async def test_execute_single_model_path(self):
        e = ModelEnsemble(ensemble_models=["deepseek/deepseek-v4-pro"])
        result = await e.execute(task=_FakeTask("test"), context={})
        assert result.method == "single"
        assert result.selected is not None

    @pytest.mark.asyncio
    async def test_execute_below_threshold(self):
        e = ModelEnsemble(ensemble_models=["m1", "m2"])
        result = await e.execute(task=_FakeTask("test"), context={}, weight=ENSEMBLE_WEIGHT_THRESHOLD)
        assert result.method == "single"

    @pytest.mark.asyncio
    async def test_execute_multi_model_mock(self):
        e = ModelEnsemble(ensemble_models=["m1", "m2"])
        result = await e.execute(task=_FakeTask("complex refactor"), context={}, weight=2.0)
        assert result.selected is not None

    @pytest.mark.asyncio
    async def test_execute_no_models(self):
        e = ModelEnsemble()
        result = await e.execute(task=_FakeTask("test"), context={})
        assert result.method == "single"

    def test_constants(self):
        assert ENSEMBLE_WEIGHT_THRESHOLD > 0
        assert 0 < FUSION_DELTA_THRESHOLD < 1
        assert MAX_ENSEMBLE_CANDIDATES > 0
