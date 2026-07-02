"""覆盖率补测——goal/ensemble.py (ModelEnsemble + JudgeScore + EnsembleResult)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.goal.ensemble import EnsembleResult, JudgeScore, ModelEnsemble


class TestJudgeScore:
    def test_defaults(self):
        js = JudgeScore()
        assert js.correctness == 0.0
        assert js.performance == 0.0
        assert js.maintainability == 0.0

    def test_total_weighted(self):
        js = JudgeScore(correctness=1.0, performance=0.8, maintainability=0.6)
        expected = 1.0 * 0.50 + 0.8 * 0.25 + 0.6 * 0.25
        assert js.total == expected

    def test_total_default_zero(self):
        js = JudgeScore()
        assert js.total == 0.0


class TestEnsembleResult:
    def test_default_single_method(self):
        result = EnsembleResult()
        assert result.method == "selection"
        assert result.is_fused is False

    def test_fusion_method(self):
        result = EnsembleResult(method="fusion")
        assert result.is_fused is True

    def test_with_scores(self):
        scores = [JudgeScore(correctness=0.9), JudgeScore(correctness=0.7)]
        result = EnsembleResult(scores=scores)
        assert len(result.scores) == 2


class TestModelEnsemble:
    def test_init(self):
        ensemble = ModelEnsemble(
            agent_factory=MagicMock(),
            judge_llm=MagicMock(),
            ensemble_models=["claude-opus", "gpt-4o"],
        )
        assert ensemble._models == ["claude-opus", "gpt-4o"]

    def test_init_default_models(self):
        ensemble = ModelEnsemble(
            agent_factory=MagicMock(),
            judge_llm=MagicMock(),
        )
        assert ensemble._models == []

    def test_init_threshold(self):
        ensemble = ModelEnsemble(
            agent_factory=MagicMock(),
            judge_llm=MagicMock(),
            weight_threshold=0.8,
        )
        assert ensemble._threshold == 0.8

    @pytest.mark.asyncio
    async def test_execute_no_models(self):
        """无集成模型——execute 需要 agent_factory mock。"""
        mock_factory = MagicMock()
        mock_agent = AsyncMock()
        mock_agent.execute = AsyncMock(return_value=MagicMock(output="fallback"))
        mock_factory.create = MagicMock(return_value=mock_agent)

        ensemble = ModelEnsemble(
            agent_factory=mock_factory,
            judge_llm=MagicMock(),
            ensemble_models=[],
        )
        task = type("Task", (), {"description": "test", "id": "t1"})()
        result = await ensemble.execute(task, context={})
        assert isinstance(result, EnsembleResult)
        assert result.method != "fusion"
