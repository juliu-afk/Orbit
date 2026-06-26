"""压缩数据模型 (Phase 2 AC7+AC8).

Token 预算 + 双阈值 + 压缩结果.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CompressionAction(StrEnum):
    """压缩动作——双阈值判定结果."""

    SKIP = "skip"  # 低于 50%——无操作
    WARN = "warn"  # 50-85%——后台摘要
    FORCE = "force"  # 超过 85%——强制压缩
    FORK = "fork"  # 压缩后仍超 85%——子 Session 分叉


class CompressionThreshold(BaseModel):
    """双阈值配置——50% 软警告 / 85% 硬限制.

    WHY 50/85: 50% 给 2-3 轮工具调用留余量，85% 确保不超上下文窗口。
    """

    soft_warning: float = Field(0.50, ge=0.0, le=1.0)
    hard_limit: float = Field(0.85, ge=0.0, le=1.0)


class CompressionResult(BaseModel):
    """一次压缩的结果."""

    action: CompressionAction
    original_tokens: int = 0
    compressed_tokens: int = 0
    ratio: float = 0.0  # 压缩比 (e.g. 0.65 = 65% 减少)
    child_session_id: str | None = None  # FORK 时设置
    layers_applied: list[str] = Field(default_factory=list)
    compressible_bytes_removed: int = 0


class TokenEstimate(BaseModel):
    """单条消息的 token 估算."""

    role: str
    estimated_tokens: int = 0
    char_count: int = 0


class TokenBudget(BaseModel):
    """每个 Session 的 token 预算.

    WHY reserved_output: 必须留 token 给 LLM 响应，不能全用给输入。
    """

    max_context_window: int = 128_000  # 模型上下文窗口
    reserved_output: int = 4096  # 留给 LLM 响应的 token
    current_usage: int = 0  # 当前估算 token 用量
    threshold: CompressionThreshold = Field(default_factory=CompressionThreshold)

    @property
    def available(self) -> int:
        """剩余可用 token."""
        return max(0, self.max_context_window - self.reserved_output - self.current_usage)

    @property
    def usage_ratio(self) -> float:
        """使用率 (0.0-1.0+)."""
        denom = self.max_context_window - self.reserved_output
        if denom <= 0:
            return 1.0
        return self.current_usage / denom
