"""ResourceGuard 数据模型 (Step 7.3).

纯 dataclass，被 token_bucket/budget_guard/degradation/resource_guard 共用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GuardDecision(StrEnum):
    """资源守卫决策。"""

    ALLOW = "allow"  # 放行
    DENY = "deny"  # 拒绝（触发降级）


class CircuitState(StrEnum):
    """熔断器三态。"""

    CLOSED = "CLOSED"  # 正常通行
    OPEN = "OPEN"  # 熔断打开，拒绝所有请求
    HALF_OPEN = "HALF_OPEN"  # 半开探测，限量放行


@dataclass
class GuardResult:
    """ResourceGuard.guard_request() 返回结果。"""

    decision: GuardDecision
    reason: str = ""  # 拒绝原因（供日志/告警）
    degradation_level: int = 0  # 0=未降级, 1-4=降级级数
    degradation_path: str = ""  # L1_BACKUP_MODEL | L2_RULE_ENGINE | ...


@dataclass
class BudgetRecord:
    """单任务 Token 预算记录。"""

    budget: int  # 预算上限（token 数）
    used: int = 0  # 已消耗
    tripped: bool = False  # 是否已触发熔断


@dataclass
class ResourceGuardState:
    """ResourceGuard 完整状态快照。"""

    token_bucket_available: float  # 当前可用令牌数
    token_bucket_capacity: float
    active_budgets: int  # 活跃预算数
    tripped_budgets: int  # 已熔断预算数
    degradation_stats: dict[str, int] = field(default_factory=dict)
    # { L1_BACKUP_MODEL: count, L2_RULE_ENGINE: count, ... }

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_bucket_available": self.token_bucket_available,
            "token_bucket_capacity": self.token_bucket_capacity,
            "active_budgets": self.active_budgets,
            "tripped_budgets": self.tripped_budgets,
            "degradation_stats": self.degradation_stats,
        }
