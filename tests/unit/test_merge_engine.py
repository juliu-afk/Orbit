"""MergeEngine unit tests - pure functions coverage."""
from __future__ import annotations

import pytest

from orbit.scheduler.merge_engine import EVALUATION_DIMENSIONS, MergeEngine, MergeResult


class TestMergeEngineInit:
    def test_init_no_llm(self):
        e = MergeEngine(None)
        assert e is not None


class TestEvaluationDimensions:
    def test_all_six_dimensions(self):
        assert len(EVALUATION_DIMENSIONS) == 6

    def test_weights_sum_to_100(self):
        total = sum(d["weight"] for d in EVALUATION_DIMENSIONS)
        assert total == 100

    def test_each_has_checks(self):
        for d in EVALUATION_DIMENSIONS:
            assert len(d["deterministic_checks"]) > 0

    def test_key_dimensions_present(self):
        keys = {d["key"] for d in EVALUATION_DIMENSIONS}
        assert "correctness" in keys
        assert "security" in keys
        assert "maintainability" in keys


class TestMergeResult:
    def test_defaults(self):
        r = MergeResult()
        assert r.selected_branch == ""
        assert r.merged_content == ""

    def test_with_scores(self):
        r = MergeResult(
            selected_branch="main", merged_content="code",
            dimension_scores={"correctness": 90}, winner="main",
        )
        assert r.winner == "main"


class TestDeterministicCheck:
    def test_empty_output(self):
        e = MergeEngine(None)
        result = e._deterministic_check({}, "task")
        assert isinstance(result, dict)
        assert "correctness" in result

    def test_ok_output_scores_high(self):
        e = MergeEngine(None)
        result = e._deterministic_check({"status": "ok", "result": {"code": "print(1)"}}, "task")
        assert result["correctness"] > 0

    def test_empty_output_scores_zero(self):
        e = MergeEngine(None)
        result = e._deterministic_check({}, "")
        assert result["correctness"] == 0.0


class TestBuildPrompts:
    def test_build_evaluation_prompt(self):
        e = MergeEngine(None)
        prompt = e._build_evaluation_prompt("output1", "output2", "task")
        assert len(prompt) > 0
        assert "output1" in prompt

    def test_build_synthesis_prompt(self):
        e = MergeEngine(None)
        prompt = e._build_synthesis_prompt("best", "other", {"correctness": 90})
        assert len(prompt) > 0


class TestParseScores:
    def test_parse_valid_json(self):
        e = MergeEngine(None)
        dims = EVALUATION_DIMENSIONS
        scores = e._parse_scores('{"correctness": 90, "completeness": 80, "security": 85, "maintainability": 75, "performance": 70, "simplicity": 80}', dims)
        assert scores["correctness"] == 90
        assert scores["security"] == 85

    def test_parse_invalid_json(self):
        e = MergeEngine(None)
        scores = e._parse_scores("not json", EVALUATION_DIMENSIONS)
        # 降级——所有维度给 50
        assert all(v == 50 for v in scores.values())


class TestFallbackMerge:
    def test_fallback_no_attempts(self):
        e = MergeEngine(None)
        result = e._fallback_merge([])
        assert result.selected_branch == "fallback"
        assert result.winner == "none"

    def test_tier_label(self):
        r = MergeResult(selected_branch="b", winner="w")
        r.tier = 1
        assert "Tier 1" in r.tier_label
