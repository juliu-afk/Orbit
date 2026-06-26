"""merge_engine.py unit tests — 覆盖 P0-2 coverage gap."""

from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.router.agent import ModelTier
from orbit.scheduler.escalation import TierAttempt
from orbit.scheduler.merge_engine import (
    EVALUATION_DIMENSIONS,
    DimensionScore,
    MergeEngine,
    MergeResult,
)


class TestDeterministicCheck:
    def test_normal_output(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({"code": "def f(): return 1"}, "task")
        assert scores["syntax_valid"] == 10.0
        assert scores["status_is_ok"] == 10.0
        assert scores["no_eval"] == 10.0

    def test_empty_dict_output(self):
        engine = MergeEngine(llm_client=None)
        # empty dict → str({}) = "{}" which is non-empty. Test with truly empty content.
        scores = engine._deterministic_check({"code": ""}, "task")
        # str output includes dict repr so it's non-empty. Score is 10 for non-empty.
        assert scores["no_empty_output"] == 10.0

    def test_status_error(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({"status": "failed"}, "task")
        assert scores["status_is_ok"] == 0.0

    def test_contains_eval(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({"code": "eval('1+1')"}, "task")
        assert scores["no_eval"] == 0.0

    def test_hardcoded_secret(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({"code": "sk-1234secret"}, "task")
        assert scores["no_hardcoded_secret"] == 0.0

    def test_has_error_handling(self):
        engine = MergeEngine(llm_client=None)
        scores = engine._deterministic_check({"code": "try:\n  pass\nexcept:\n  pass"}, "task")
        assert scores["has_error_handling"] == 10.0


class TestParseScores:
    def test_parses_valid_json(self):
        engine = MergeEngine(llm_client=None)
        raw = _json.dumps(
            {
                "evaluations": {
                    "tier_1": {
                        "correctness": {"score": 8, "reason": "ok", "best_of": None},
                    },
                },
            }
        )
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "x"}, success=True)
        ]
        scored = engine._parse_scores(raw, attempts)
        assert "tier_1" in scored
        assert len(scored["tier_1"]) == 6  # all 6 dimensions

    def test_missing_dimension_defaults(self):
        engine = MergeEngine(llm_client=None)
        raw = _json.dumps({"evaluations": {"tier_1": {}}})
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "x"}, success=True)
        ]
        scored = engine._parse_scores(raw, attempts)
        assert scored["tier_1"][0].score == 5.0  # default


class TestBuildEvaluationPrompt:
    def test_contains_dimensions(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "x"}, success=True),
        ]
        det_scores = {"tier_1": {"syntax_valid": 10.0}}
        prompt = engine._build_evaluation_prompt(attempts, "task", det_scores)
        assert "正确性" in prompt
        assert "syntax_valid" in prompt

    def test_contains_all_dims(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "x"}, success=True)
        ]
        det_scores = {"tier_1": {}}
        prompt = engine._build_evaluation_prompt(attempts, "task", det_scores)
        for dim in EVALUATION_DIMENSIONS:
            assert dim["name"] in prompt


class TestBuildSynthesisPrompt:
    def test_contains_scorecard_table(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m1", output={"code": "a"}, success=True),
            TierAttempt(tier=ModelTier.TIER_2, model="m2", output={"code": "b"}, success=True),
        ]
        scores = {}
        for a in attempts:
            scores[a.tier_label] = [
                DimensionScore(key=d["key"], score=7, reason="ok") for d in EVALUATION_DIMENSIONS
            ]
        prompt = engine._build_synthesis_prompt(attempts, scores, "task")
        assert "评分卡" in prompt
        assert "|" in prompt  # table


class TestMergeSingleAttempt:
    @pytest.mark.asyncio
    async def test_returns_single_directly(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "solo"}, success=True),
        ]
        result = await engine.merge(attempts, "task")
        assert result.merged == {"code": "solo"}
        assert result.scorer == "n/a (single attempt)"

    @pytest.mark.asyncio
    async def test_uses_first_with_output(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output=None, success=False),
            TierAttempt(tier=ModelTier.TIER_2, model="m", output={"code": "only"}, success=True),
        ]
        result = await engine.merge(attempts, "task")
        assert result.merged == {"code": "only"}


class TestFallbackMerge:
    def test_returns_t3_on_fallback(self):
        engine = MergeEngine(llm_client=None)
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m1", output={"code": "a"}, success=True),
            TierAttempt(tier=ModelTier.TIER_3, model="m3", output={"code": "c"}, success=True),
        ]
        result = engine._fallback_merge(attempts)
        assert result.merged == {"code": "c"}
        assert "fallback" in result.scorer


class TestDimensionScore:
    def test_creation(self):
        ds = DimensionScore(key="test", score=7.5, reason="good", best_of=None)
        assert ds.score == 7.5
        assert ds.key == "test"


class TestMergeResult:
    def test_defaults(self):
        mr = MergeResult(
            merged={},
            scorer="gpt",
            scorecard={},
            taken_from={},
            gaps_filled=[],
            total_scores={},
        )
        assert mr.merged == {}


class TestEvalDimensions:
    def test_total_weight_100(self):
        total = sum(d["weight"] for d in EVALUATION_DIMENSIONS)
        assert total == 100

    def test_six_dimensions(self):
        assert len(EVALUATION_DIMENSIONS) == 6
