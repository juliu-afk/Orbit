"""高峰避让调度数据模型。

WHY 独立 models 文件: OffPeakScheduler/DeferredQueue/PeakWindowManager 各自引用
这些模型——集中定义避免循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

# DeferredTask status 约束类型
DeferredStatus = Literal[
    "queued", "released", "running", "done", "urgent_override", "cancelled"
]


@dataclass
class PeakWindow:
    """单个时段定义——一天中的某个时间段。

    WHY dataclass 而非 Pydantic: 纯数据载体——不需要校验/序列化，
    遵循 SessionRecord/ProjectRecord 的 dataclass 惯例。
    """

    days: list[str]
    hours_start: str
    hours_end: str
    # 由 next_offpeak_window() 填充——具体时段的 UTC ISO 时间
    starts_at_iso: str = ""
    ends_at_iso: str = ""

    def contains(self, day_name: str, time_str: str) -> bool:
        """判定给定星期和时间是否在此窗口内。"""
        return day_name in self.days and self.hours_start <= time_str < self.hours_end


@dataclass
class ProviderPeakConfig:
    """单个 LLM 厂商的高峰/低峰配置。"""

    provider: str  # "deepseek" | "anthropic" | "openai" | "glm"
    timezone: str  # "Asia/Shanghai" | "America/Los_Angeles"
    peak_windows: list[PeakWindow] = field(default_factory=list)
    offpeak_windows: list[PeakWindow] = field(default_factory=list)
    peak_price_multiplier: float = 1.0
    offpeak_price_multiplier: float = 1.0


@dataclass
class DeferredTask:
    """延迟执行任务——持久化到 deferred_tasks 表。

    对应 PRD 4.2 DeferredTask 模型。
    """

    id: str  # = GoalSession.id
    goal_description: str = ""
    priority: str = "NORMAL"  # CRITICAL|HIGH|NORMAL|LOW
    provider: str = ""  # deepseek|anthropic|openai|glm
    estimated_tokens: int = 0
    estimated_duration_seconds: int = 0
    target_window_start: str = ""  # ISO datetime
    target_window_end: str = ""  # ISO datetime
    status: DeferredStatus = "queued"
    created_at: str = ""
    released_at: str | None = None
    completed_at: str | None = None
    actual_tokens: int = 0
    cost_saved_yuan: float = 0.0
    goal_json: str = ""  # GoalSession 序列化——窗口到达时反序列化

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class EnqueueResult:
    """入队结果——返回给 API 调用方。"""

    goal_id: str
    status: str  # "queued" | "peak_warning"
    target_window_start: str = ""
    target_window_end: str = ""
    queue_position: int = 0
    warning_message: str = ""  # 高峰警告时填充


@dataclass
class PeakStatus:
    """单个厂商的高峰状态。"""

    provider: str
    is_peak: bool
    peak_ends_at: str | None = None
    next_offpeak_starts_at: str | None = None
    next_offpeak_ends_at: str | None = None
    offpeak_duration_hours: float = 0.0
