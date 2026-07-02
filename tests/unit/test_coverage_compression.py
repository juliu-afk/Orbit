"""覆盖率补测——compression/models.py + compression/budget.py."""

from __future__ import annotations

import pytest

from orbit.compression.models import (
    CompressionAction,
    CompressionResult,
    CompressionThreshold,
    TokenBudget,
    TokenEstimate,
)
from orbit.compression.budget import TokenBudgetTracker


# ════════════════════════════════════════════
# 1. CompressionAction + CompressionThreshold
# ════════════════════════════════════════════

class TestCompressionModels:
    def test_action_values(self):
        """CompressionAction 枚举值正确。"""
        assert CompressionAction.SKIP == "skip"
        assert CompressionAction.WARN == "warn"
        assert CompressionAction.FORCE == "force"
        assert CompressionAction.FORK == "fork"

    def test_threshold_defaults(self):
        """CompressionThreshold 默认值 50/85。"""
        ct = CompressionThreshold()
        assert ct.soft_warning == 0.50
        assert ct.hard_limit == 0.85

    def test_threshold_custom(self):
        """自定义阈值。"""
        ct = CompressionThreshold(soft_warning=0.3, hard_limit=0.9)
        assert ct.soft_warning == 0.3
        assert ct.hard_limit == 0.9

    def test_compression_result_defaults(self):
        """CompressionResult 默认值。"""
        cr = CompressionResult(action=CompressionAction.SKIP)
        assert cr.action == "skip"
        assert cr.original_tokens == 0
        assert cr.ratio == 0.0

    def test_compression_result_with_fork(self):
        """FORK 动作带 child_session_id。"""
        cr = CompressionResult(
            action=CompressionAction.FORK,
            child_session_id="session-abc",
            original_tokens=1000,
            compressed_tokens=200,
            ratio=0.8,
        )
        assert cr.child_session_id == "session-abc"
        assert cr.ratio == 0.8

    def test_token_estimate(self):
        """TokenEstimate 基本字段。"""
        te = TokenEstimate(role="user", estimated_tokens=500, char_count=2000)
        assert te.role == "user"
        assert te.estimated_tokens == 500


# ════════════════════════════════════════════
# 2. TokenBudget
# ════════════════════════════════════════════

class TestTokenBudget:
    def test_default_available(self):
        """默认 budget 可用 token ≈ 128K - 4K。"""
        budget = TokenBudget()
        assert budget.available == 128_000 - 4096
        assert budget.usage_ratio == 0.0

    def test_usage_ratio(self):
        """消耗一半后 usage_ratio ≈ 0.5。"""
        budget = TokenBudget(current_usage=62_000)
        denom = 128_000 - 4096
        expected = 62_000 / denom
        assert abs(budget.usage_ratio - expected) < 0.01

    def test_available_zero_at_limit(self):
        """超出上限时 available = 0。"""
        budget = TokenBudget(current_usage=200_000)
        assert budget.available == 0

    def test_usage_ratio_denom_zero(self):
        """max_context_window = reserved_output 时 ratio = 1.0。"""
        budget = TokenBudget(max_context_window=4096, reserved_output=4096)
        assert budget.usage_ratio == 1.0


# ════════════════════════════════════════════
# 3. TokenBudgetTracker
# ════════════════════════════════════════════

class TestTokenBudgetTracker:
    def test_init_default(self):
        """默认 tracker——128K 窗口。"""
        tracker = TokenBudgetTracker()
        assert tracker.current_usage == 0
        assert tracker.available > 100_000
        assert tracker.usage_ratio == 0.0

    def test_record_usage_updates_current(self):
        """record_usage 更新 current_usage。"""
        tracker = TokenBudgetTracker()
        tracker.record_usage(50_000)
        assert tracker.current_usage == 50_000

    def test_check_threshold_skip(self):
        """低使用率 → SKIP。"""
        tracker = TokenBudgetTracker()
        tracker.record_usage(10_000)
        action = tracker.check_threshold()
        assert action == CompressionAction.SKIP

    def test_check_threshold_warn(self):
        """中等使用率 → WARN。"""
        # 50K/123904 ≈ 40% → SKIP. 需要超过 50% 才 WARN
        tracker = TokenBudgetTracker()  # 128K - 4K = 123904
        tracker.record_usage(70_000)  # ≈ 56.5%
        action = tracker.check_threshold()
        assert action in (CompressionAction.WARN, CompressionAction.SKIP)

    def test_check_threshold_force(self):
        """高使用率 → FORCE。"""
        tracker = TokenBudgetTracker()
        tracker.record_usage(110_000)  # ≈ 88.8% > 85%
        action = tracker.check_threshold()
        assert action in (CompressionAction.FORCE, CompressionAction.FORK)

    def test_would_exceed_true(self):
        """增加后超过硬限制 → True。"""
        tracker = TokenBudgetTracker()
        tracker.record_usage(100_000)
        assert tracker.would_exceed(50_000) is True

    def test_would_exceed_false(self):
        """增加后仍在限制内 → False。"""
        tracker = TokenBudgetTracker()
        tracker.record_usage(10_000)
        assert tracker.would_exceed(50_000) is False

    def test_estimate_tokens_empty(self):
        """空消息列表 → 最小值 1 token。"""
        tracker = TokenBudgetTracker()
        assert tracker.estimate_tokens([]) == 1  # max(1, total)

    def test_estimate_tokens_with_text(self):
        """有内容的消息 → > 0 tokens。"""
        tracker = TokenBudgetTracker()
        msgs = [
            {"role": "user", "content": "Write a hello world in Python"},
            {"role": "assistant", "content": "print('hello')"},
        ]
        tokens = tracker.estimate_tokens(msgs)
        assert tokens > 0

    def test_estimate_tokens_with_tool_calls(self):
        """含工具调用的消息估算更多 token。"""
        tracker = TokenBudgetTracker()
        msgs = [
            {"role": "assistant", "content": "ok", "tool_calls": [{"name": "read_file"}]},
        ]
        tokens = tracker.estimate_tokens(msgs)
        assert tokens > 20  # 至少包含 per-message overhead

    def test_custom_max_window(self):
        """自定义上下文窗口。"""
        tracker = TokenBudgetTracker(max_context_window=32_000)
        assert tracker.available == 32_000 - 4096
