"""覆盖率补测——compression/cascade.py (CascadePruner)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.compression.cascade import (
    CONSUMED_OUTPUT_MAX_TURNS,
    DEFAULT_LARGE_OUTPUT_THRESHOLD,
    INEFFECTUAL_MIN_CHARS,
    LARGE_OUTPUT_THRESHOLD,
    CascadePruner,
)
from orbit.compression.budget import TokenBudgetTracker
from orbit.compression.models import CompressionAction, CompressionThreshold


class TestConstants:
    def test_thresholds_positive(self):
        assert DEFAULT_LARGE_OUTPUT_THRESHOLD > 0
        assert CONSUMED_OUTPUT_MAX_TURNS > 0
        assert INEFFECTUAL_MIN_CHARS > 0
        assert LARGE_OUTPUT_THRESHOLD == DEFAULT_LARGE_OUTPUT_THRESHOLD


class TestCascadePruner:
    def test_init_defaults(self):
        pruner = CascadePruner()
        assert pruner._large_threshold == DEFAULT_LARGE_OUTPUT_THRESHOLD
        assert pruner._consumed_turns == CONSUMED_OUTPUT_MAX_TURNS
        assert pruner._ineffectual_min == INEFFECTUAL_MIN_CHARS
        assert pruner.stages_applied == []
        assert pruner.bytes_removed == 0

    def test_init_custom(self):
        pruner = CascadePruner(
            large_output_threshold=1000,
            consumed_output_max_turns=5,
            ineffectual_min_chars=50,
        )
        assert pruner._large_threshold == 1000
        assert pruner._consumed_turns == 5
        assert pruner._ineffectual_min == 50

    @pytest.mark.asyncio
    async def test_prune_if_needed_no_budget(self):
        """budget=None → 直接返回原消息。"""
        pruner = CascadePruner()
        msgs = [{"role": "user", "content": "hi"}]
        result, stages, removed = await pruner.prune_if_needed(msgs, None, None)
        assert result == msgs
        assert stages == []

    @pytest.mark.asyncio
    async def test_prune_if_needed_below_threshold(self):
        """低于 FORCE 阈值 → SKIP，不裁剪。"""
        pruner = CascadePruner()
        msgs = [{"role": "user", "content": "hi"}]
        budget = TokenBudgetTracker(max_context_window=128_000)
        budget.record_usage(1000)  # 远低于阈值
        result, stages, removed = await pruner.prune_if_needed(msgs, None, budget)
        assert result == msgs  # 无变更

    @pytest.mark.asyncio
    async def test_prune_if_needed_force_threshold(self):
        """超过 FORCE 阈值 → 触发 Stage 1 裁剪。"""
        pruner = CascadePruner()
        msgs = [{"role": "user", "content": "x"}]
        budget = TokenBudgetTracker(max_context_window=128_000)
        budget.record_usage(120_000)  # ≈97% 超过 85% hard_limit
        result, stages, removed = await pruner.prune_if_needed(msgs, None, budget)
        assert isinstance(result, list)
        assert "strip_consumed" in stages

    def test_is_consumed_no_content(self):
        """无内容或空内容的工具消息 → 未消费。"""
        pruner = CascadePruner()
        msg = {"role": "tool", "content": ""}
        msgs = [msg]
        assert pruner._is_consumed(msg, msgs, 0) is False

    def test_is_consumed_with_assistant_response(self):
        """后续有 assistant 响应 → 已消费。"""
        pruner = CascadePruner()
        msgs = [
            {"role": "tool", "content": "file content here"},
            {"role": "assistant", "content": "Based on the file content, I will now refactor..."},
        ]
        assert pruner._is_consumed(msgs[0], msgs, 0) is True

    def test_is_error_output(self):
        """检测错误输出。"""
        assert CascadePruner._is_error_output("Error: something failed") is True
        assert CascadePruner._is_error_output("Traceback (most recent call last)") is True
        assert CascadePruner._is_error_output("All tests passed") is False
        assert CascadePruner._is_error_output("") is False
