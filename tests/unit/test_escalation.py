"""escalation.py unit tests — 覆盖 P0-2 coverage gap."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.router.agent import ModelTier
from orbit.scheduler.escalation import (
    EscalationResult,
    TierAttempt,
    build_merge_prompt,
    merge_outputs,
    needs_escalation,
    next_tier,
)


class TestNeedsEscalation:
    def test_error_triggers_escalation(self):
        assert needs_escalation(None, "some error") is True

    def test_none_output_triggers_escalation(self):
        assert needs_escalation(None, None) is True

    def test_failed_status_triggers_escalation(self):
        assert needs_escalation({"status": "error"}, None) is True
        assert needs_escalation({"status": "failed"}, None) is True
        assert needs_escalation({"status": "invalid"}, None) is True

    def test_ok_status_no_escalation(self):
        assert needs_escalation({"status": "ok"}, None) is False

    def test_default_status_no_escalation(self):
        assert needs_escalation({"code": "def f(): pass"}, None) is False


class TestNextTier:
    def test_full_chain(self):
        assert next_tier(ModelTier.TIER_0) == ModelTier.TIER_1
        assert next_tier(ModelTier.TIER_1) == ModelTier.TIER_2
        assert next_tier(ModelTier.TIER_2) == ModelTier.TIER_3

    def test_tier3_returns_none(self):
        assert next_tier(ModelTier.TIER_3) is None


class TestBuildMergePrompt:
    def test_builds_prompt_with_three_attempts(self):
        attempts = [
            TierAttempt(
                tier=ModelTier.TIER_1, model="ds-flash", output={"code": "x=1"}, success=True
            ),
            TierAttempt(
                tier=ModelTier.TIER_2, model="ds-pro", output={"code": "x=2"}, success=True
            ),
            TierAttempt(
                tier=ModelTier.TIER_3, model="glm-5.2", output={"code": "x=3"}, success=True
            ),
        ]
        prompt = build_merge_prompt(attempts, "test task")
        assert "Tier1-DS Flash" in prompt
        assert "Tier2-DS V4 Pro" in prompt
        assert "Tier3-GLM-5.2" in prompt
        assert "合并要求" in prompt
        assert "test task" in prompt

    def test_long_output_truncated(self):
        long_code = "x" * 5000
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": long_code}, success=True),
        ]
        prompt = build_merge_prompt(attempts, "task")
        assert "...(截断)" in prompt

    def test_includes_error_status(self):
        attempts = [
            TierAttempt(
                tier=ModelTier.TIER_1, model="m", output=None, error="timeout", success=False
            ),
        ]
        prompt = build_merge_prompt(attempts, "task")
        assert "timeout" in prompt


class TestMergeOutputs:
    @pytest.mark.asyncio
    async def test_returns_single_output(self):
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m", output={"code": "ok"}, success=True),
        ]
        result = await merge_outputs(None, attempts, "task")
        assert result == {"code": "ok"}

    @pytest.mark.asyncio
    async def test_calls_llm_for_multiple(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(
            return_value=MagicMock(content='{"merged": {"code": "best"}, "taken_from": {}}')
        )
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m1", output={"code": "a"}, success=True),
            TierAttempt(tier=ModelTier.TIER_2, model="m2", output={"code": "b"}, success=True),
        ]
        result = await merge_outputs(mock_llm, attempts, "task")
        assert result == {"merged": {"code": "best"}, "taken_from": {}}

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("boom"))
        attempts = [
            TierAttempt(tier=ModelTier.TIER_1, model="m1", output={"code": "a"}, success=True),
            TierAttempt(tier=ModelTier.TIER_2, model="m2", output={"code": "b"}, success=False),
        ]
        result = await merge_outputs(mock_llm, attempts, "task")
        assert result == {"code": "a"}  # fallback to only successful


class TestTierAttempt:
    def test_tier_label_property(self):
        a = TierAttempt(tier=ModelTier.TIER_2, model="m")
        assert a.tier_label == "tier_2"

    def test_frozen(self):
        a = TierAttempt(tier=ModelTier.TIER_1, model="m")
        with pytest.raises(FrozenInstanceError):
            a.tier = ModelTier.TIER_3  # type: ignore[misc]


class TestEscalationResult:
    def test_default_values(self):
        r = EscalationResult()
        assert r.attempts == []
        assert r.merged_output is None
        assert r.final_status == "unknown"
