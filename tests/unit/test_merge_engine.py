"""MergeEngine unit tests - pure functions coverage."""
from __future__ import annotations

import pytest

from orbit.scheduler.merge_engine import EVALUATION_DIMENSIONS, MergeEngine, MergeResult
from orbit.scheduler.escalation import TierAttempt


class TestMergeEngineInit:
    def test_init(self):
        from unittest.mock import MagicMock
        e = MergeEngine(MagicMock())
        assert e is not None
        assert e.llm is not None


class TestEvaluationDimensions:
    def test_six_dimensions(self):
        assert len(EVALUATION_DIMENSIONS) == 6

    def test_weights_sum_to_100(self):
        total = sum(d["weight"] for d in EVALUATION_DIMENSIONS)
        assert total == 100

    def test_keys(self):
        keys = {d["key"] for d in EVALUATION_DIMENSIONS}
        assert "correctness" in keys
        assert "security" in keys


class TestMergeResult:
    def test_create(self):
        r = MergeResult(
            merged={}, scorer="test", scorecard={},
            taken_from={}, gaps_filled=[], total_scores={},
        )
        assert r.scorer == "test"


class TestDeterministicCheck:
    def test_empty_output(self):
        e = MergeEngine(None)
        result = e._deterministic_check({}, "")
        assert result["syntax_valid"] == 0.0
        assert result["no_empty_output"] == 0.0

    def test_ok_output(self):
        e = MergeEngine(None)
        result = e._deterministic_check({"status": "ok"}, "some task description here")
        assert result["status_is_ok"] == 10.0
        assert result["syntax_valid"] == 10.0

    def test_risky_content(self):
        e = MergeEngine(None)
        result = e._deterministic_check({}, "eval(something)")
        assert result["no_eval"] == 0.0

    def test_hardcoded_secret(self):
        e = MergeEngine(None)
        result = e._deterministic_check({}, "api_key=abc123")
        assert result["no_hardcoded_secret"] == 0.0

    def test_error_handling_detected(self):
        e = MergeEngine(None)
        # 错误处理检查仅看 output 内容，task 不参与此检查
        result = e._deterministic_check({"code": "try:\n  foo()\nexcept:\n  pass"}, "")
        assert result["has_error_handling"] == 10.0


class TestBuildPrompts:
    def test_evaluation_prompt(self):
        e = MergeEngine(None)
        prompt = e._build_evaluation_prompt([], "task", {})
        assert len(prompt) > 0

    def test_synthesis_prompt(self):
        e = MergeEngine(None)
        prompt = e._build_synthesis_prompt([], {}, "task")
        assert len(prompt) > 0


class TestParseScores:
    def test_parse(self):
        e = MergeEngine(None)
        # Create a mock TierAttempt
        from dataclasses import dataclass
        @dataclass
        class FakeAttempt:
            tier_label: str = "Tier 1"
            output: dict | None = None
        scores = e._parse_scores('{"evaluations": {"Tier 1": {"correctness": {"score": 9, "reason": "good"}}}}', [FakeAttempt()])
        assert "Tier 1" in scores

    def test_parse_invalid(self):
        e = MergeEngine(None)
        from dataclasses import dataclass
        @dataclass
        class FakeAttempt:
            tier_label: str = "Tier 1"
            output: dict | None = None
        scores = e._parse_scores("not json", [FakeAttempt()])
        assert isinstance(scores, dict)


class TestFallbackMerge:
    def test_fallback(self):
        e = MergeEngine(None)
        from dataclasses import dataclass, field
        @dataclass
        class FakeAttempt:
            tier_label: str = "Tier 1"
            output: dict | None = field(default_factory=lambda: {"code": "ok"})
        result = e._fallback_merge([FakeAttempt()])
        assert "fallback" in result.scorer
