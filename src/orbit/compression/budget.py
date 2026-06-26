"""Token 预算跟踪器 (Phase 2 AC8).

跟踪每个 Session 的 token 使用量，判断是否触发压缩。
WHY chars/4 而非 tiktoken: 零依赖零延迟，±20% 误差在 128K 窗口下安全。
"""

from __future__ import annotations

from typing import Any

from orbit.compression.models import CompressionAction, CompressionThreshold, TokenBudget


class TokenBudgetTracker:
    """Token 预算跟踪器——估算 + 阈值判定.

    Usage:
        tracker = TokenBudgetTracker(max_context_window=128_000)
        tracker.record_usage(estimated_tokens=45_000)
        action = tracker.check_threshold()  # → CompressionAction.SKIP
    """

    def __init__(
        self,
        max_context_window: int = 128_000,
        reserved_output: int = 4096,
        threshold: CompressionThreshold | None = None,
    ) -> None:
        self._budget = TokenBudget(
            max_context_window=max_context_window,
            reserved_output=reserved_output,
            threshold=threshold or CompressionThreshold(),
        )

    # ── 公共 API ──────────────────────────────────────

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的 token 数.

        WHY chars/4: GPT tokenizer 大约 1 token = 4 英文字符。
        中文字符约 1.5-2 token/字，chars/4 对中文略微低估，但在 128K 窗口下安全。
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                total += len(content) // 4
                # per-message overhead: role 标记 + 格式化
                total += 20
            # tool_calls 也消耗 token
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total += len(str(tool_calls)) // 4
        return max(1, total)

    def record_usage(self, estimated_tokens: int) -> None:
        """更新当前使用量."""
        self._budget.current_usage = estimated_tokens

    def check_threshold(self) -> CompressionAction:
        """检查阈值，返回建议动作."""
        ratio = self._budget.usage_ratio
        if ratio < self._budget.threshold.soft_warning:
            return CompressionAction.SKIP
        if ratio < self._budget.threshold.hard_limit:
            return CompressionAction.WARN
        return CompressionAction.FORCE

    def would_exceed(self, additional_tokens: int) -> bool:
        """检查添加更多 token 是否会超出硬限制."""
        new_usage = self._budget.current_usage + additional_tokens
        denom = self._budget.max_context_window - self._budget.reserved_output
        if denom <= 0:
            return True
        return (new_usage / denom) >= self._budget.threshold.hard_limit

    # ── 属性 ──────────────────────────────────────────

    @property
    def available(self) -> int:
        return self._budget.available

    @property
    def usage_ratio(self) -> float:
        return self._budget.usage_ratio

    @property
    def current_usage(self) -> int:
        return self._budget.current_usage
