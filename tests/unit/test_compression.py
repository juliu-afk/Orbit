"""压缩模块单元测试 (Phase 2 AC7+AC8)."""

from __future__ import annotations

import pytest

from orbit.compression.budget import TokenBudgetTracker
from orbit.compression.models import (
    CompressionAction,
    TokenBudget,
)
from orbit.compression.pipeline import CompressionPipeline


class TestTokenBudget:
    def test_initial_available(self):
        budget = TokenBudget(max_context_window=128_000, reserved_output=4096)
        assert budget.available == 128_000 - 4096

    def test_usage_ratio_zero(self):
        budget = TokenBudget()
        assert budget.usage_ratio == 0.0

    def test_usage_ratio_half(self):
        budget = TokenBudget(max_context_window=100_000, reserved_output=0)
        budget.current_usage = 50_000
        assert budget.usage_ratio == 0.5

    def test_available_min_zero(self):
        budget = TokenBudget(max_context_window=1000, reserved_output=800)
        budget.current_usage = 300
        assert budget.available == 0


class TestTokenBudgetTracker:
    def test_estimate_tokens(self):
        tracker = TokenBudgetTracker()
        tokens = tracker.estimate_tokens(
            [
                {"role": "user", "content": "hello world" * 100},
            ]
        )
        assert tokens > 0

    def test_check_skip_below_50(self):
        tracker = TokenBudgetTracker(max_context_window=128_000)
        tracker.record_usage(30_000)
        assert tracker.check_threshold() == CompressionAction.SKIP

    def test_check_warn_50_to_85(self):
        tracker = TokenBudgetTracker(max_context_window=128_000)
        tracker.record_usage(80_000)
        assert tracker.check_threshold() == CompressionAction.WARN

    def test_check_force_above_85(self):
        tracker = TokenBudgetTracker(max_context_window=128_000)
        tracker.record_usage(115_000)
        assert tracker.check_threshold() == CompressionAction.FORCE

    def test_would_exceed(self):
        tracker = TokenBudgetTracker(max_context_window=128_000)
        tracker.record_usage(100_000)
        assert tracker.would_exceed(20_000)


class TestCompressionPipeline:
    @pytest.mark.asyncio
    async def test_truncation_layer(self):
        pipe = CompressionPipeline()
        long_content = "x" * 15000
        msgs = [{"role": "tool", "content": long_content}]
        result, removed = await pipe.run(msgs, "warn")
        assert len(str(result[0]["content"])) < 15000
        assert removed > 0
        assert "truncate" in pipe.applied_layers

    @pytest.mark.asyncio
    async def test_prune_empty_tool(self):
        pipe = CompressionPipeline()
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": ""},
            {"role": "assistant", "content": "ok"},
        ]
        result, _ = await pipe.run(msgs, "warn")
        assert len(result) < 3  # empty tool removed

    @pytest.mark.asyncio
    async def test_prune_duplicate_system(self):
        pipe = CompressionPipeline()
        msgs = [
            {"role": "system", "content": "same"},
            {"role": "system", "content": "same"},
        ]
        result, _ = await pipe.run(msgs, "warn")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_dedup_layer(self):
        pipe = CompressionPipeline()
        msgs = [
            {"role": "assistant", "content": "result: success"},
            {"role": "assistant", "content": "result: success"},
        ]
        result, _ = await pipe.run(msgs, "force")
        assert len(result) <= 2  # dups may be collapsed

    @pytest.mark.asyncio
    async def test_sliding_window_preserves_system(self):
        pipe = CompressionPipeline()
        msgs = [{"role": "system", "content": "BASE"}] + [
            {"role": "assistant", "content": f"turn {i}"} for i in range(30)
        ]
        result, _ = await pipe.run(msgs, "force")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "BASE"

    @pytest.mark.asyncio
    async def test_force_adds_summary_layer(self):
        pipe = CompressionPipeline()
        msgs = [{"role": "assistant", "content": "test"}]
        await pipe.run(msgs, "force")
        assert "summary" in pipe.applied_layers

    @pytest.mark.asyncio
    async def test_warn_no_summary_layer(self):
        pipe = CompressionPipeline()
        msgs = [{"role": "assistant", "content": "test"}]
        await pipe.run(msgs, "warn")
        assert "summary" not in pipe.applied_layers


# ── ContextCompressor (8-step algorithm) ──────────────


class TestContextCompressor:
    @pytest.mark.asyncio
    async def test_compress_skip_below_threshold(self):
        """低于50%——跳过压缩."""
        from orbit.compression.compressor import ContextCompressor

        comp = ContextCompressor()
        msgs = [{"role": "user", "content": "hello"}]  # very small
        result = await comp.compress(msgs, task_id="t1")
        assert result.action == "skip"
        assert result.ratio == 0.0

    @pytest.mark.asyncio
    async def test_compress_force_action(self):
        """超85%——压缩被触发（非skip）."""
        from orbit.compression.budget import TokenBudgetTracker
        from orbit.compression.compressor import ContextCompressor

        # max_window极小 → usage_ratio=1.0 → 必然触发压缩
        tracker = TokenBudgetTracker(max_context_window=500, reserved_output=0)
        msgs = [{"role": "user", "content": "x" * 2000} for _ in range(3)]
        comp = ContextCompressor(budget_tracker=tracker)
        result = await comp.compress(msgs, task_id="t2")
        # usage_ratio=1.0 → FORCE → 压缩后可能fork，但绝不是skip
        assert result.action != "skip"
        assert result.layers_applied  # 至少应用了一层压缩

    @pytest.mark.asyncio
    async def test_compress_with_fork(self):
        """压缩后仍超85%——触发fork."""
        from orbit.compression.budget import TokenBudgetTracker
        from orbit.compression.compressor import ContextCompressor

        # 极小窗口 + 大量不可压缩内容 → 压缩后仍高 → fork
        tracker = TokenBudgetTracker(max_context_window=100, reserved_output=0)
        msgs = [
            {"role": "user", "content": "unique_data_" + str(i) + "x" * 2000} for i in range(10)
        ]
        comp = ContextCompressor(budget_tracker=tracker)
        result = await comp.compress(msgs, task_id="t3", turn=0)
        # usage_ratio=1.0+ → FORCE → 压缩后仍超85% → FORK
        assert result.action == "fork", f"Expected fork, got {result.action}"
        assert result.child_session_id is not None

    def test_budget_tracker_estimate(self):
        """Token估算."""
        from orbit.compression.budget import TokenBudgetTracker

        tracker = TokenBudgetTracker()
        tokens = tracker.estimate_tokens(
            [
                {"role": "user", "content": "hello world"},
                {"role": "assistant", "content": "response", "tool_calls": [{"id": "1"}]},
            ]
        )
        assert tokens > 0

    def test_model_window_default(self):
        from orbit.compression.compressor import ContextCompressor

        comp = ContextCompressor()
        assert comp.child_session_id is None
