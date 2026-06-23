"""ResourceGuard 资源熔断主入口 (Step 7.3).

组合 TokenBucket + BudgetGuard + DegradationPath + CircuitBreaker (已有),
在 LLM 调用前统一判断资源预算是否放行。

决策流程:
1. 全局 TokenBucket.allow(estimated_tokens) → 不够则限流
2. BudgetGuard.is_over_budget(task_id) → 超预算则局部熔断
3. CircuitBreaker.before_call(model) → 已有 API 熔断检查
4. 任一拒绝 → DegradationPath.execute(level)
5. 全部通过 → 放行

性能目标: allow_request() P99 <12ms (纯内存, 无 IO)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from orbit.observability.metrics import orbit_circuit_breaker_state
from orbit.resource_guard.budget_guard import BudgetGuard
from orbit.resource_guard.degradation import DegradationPath, DegradationResult
from orbit.resource_guard.models import (
    CircuitState,
    GuardDecision,
    GuardResult,
    ResourceGuardState,
)
from orbit.resource_guard.token_bucket import TokenBucket

logger = structlog.get_logger("orbit.resource_guard")

# 默认配置 (PRD Step 7.3)
DEFAULT_TOKEN_CAPACITY = 100000  # 全局令牌桶容量
DEFAULT_TOKEN_RATE = 5000  # 令牌/秒
DEFAULT_BUDGET_MULTIPLIER = 1.5  # 超预算倍数触发熔断
DEFAULT_HALF_OPEN_PROBE_LIMIT = 3  # 半开状态每分钟最大试探数


class ResourceGuard:
    """资源熔断守护——全局 + 单任务双层保护。

    用法:
        guard = ResourceGuard()
        result = guard.guard_request(task_id="t1", estimated_tokens=500)
        if result.decision == GuardDecision.ALLOW:
            ...  # 正常调用 LLM
        else:
            degraded = guard.degrade(result.degradation_level, context={...})

        调用 LLM 后:
            guard.record_result(task_id="t1", success=True, tokens_used=350)
    """

    def __init__(
        self,
        token_bucket: TokenBucket | None = None,
        budget_guard: BudgetGuard | None = None,
        degradation: DegradationPath | None = None,
    ) -> None:
        self._bucket = token_bucket or TokenBucket(
            capacity=DEFAULT_TOKEN_CAPACITY, rate=DEFAULT_TOKEN_RATE
        )
        self._budget = budget_guard or BudgetGuard(budget_multiplier=DEFAULT_BUDGET_MULTIPLIER)
        self._degradation = degradation or DegradationPath()

        # 熔断状态追踪
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._open_at: float | None = None
        self._half_open_probes: int = 0

        # 审计事件记录
        self._audit_events: list[dict[str, Any]] = []
        # 降级统计
        self._degradation_stats: dict[str, int] = {}

    # ── 核心 API ──────────────────────────────────────────

    def guard_request(self, task_id: str, estimated_tokens: int = 500) -> GuardResult:
        """请求放行——检查资源预算。

        Returns:
            GuardResult(decision=ALLOW/DENY, reason=..., degradation_level=...)
        """
        # 1. 全局令牌桶
        if not self._bucket.allow(estimated_tokens):
            return self._deny("TOKEN_BUCKET_EMPTY", level=1)

        # 2. 单任务预算
        if self._budget.is_over_budget(task_id):
            return self._deny("TASK_TOKEN_EXCEEDED", level=1)

        # 3. 熔断状态检查
        if self._state == CircuitState.OPEN:
            if not self._should_enter_half_open():
                return self._deny("CIRCUIT_OPEN", level=2)
            # 进入半开探测
            self._state = CircuitState.HALF_OPEN
            self._half_open_probes = 0
            logger.info("circuit_half_open_entered")

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下限量放行探测请求
            self._half_open_probes += 1
            if self._half_open_probes > DEFAULT_HALF_OPEN_PROBE_LIMIT:
                return self._deny("HALF_OPEN_PROBE_LIMIT", level=2)

        # 全部通过
        return GuardResult(decision=GuardDecision.ALLOW)

    def record_result(self, task_id: str, success: bool, tokens_used: int = 0) -> None:
        """记录调用结果——更新熔断状态 + Token 预算。

        每次 LLM 调用后必须调用此方法。
        """
        # 更新 Token 预算
        if tokens_used > 0:
            self._budget.record_usage(task_id, tokens_used)

        now = time.time()

        if success:
            self._failure_count = 0
            # 半开恢复
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._half_open_probes = 0
                logger.info("circuit_closed_after_half_open_success")
        else:
            self._failure_count += 1
            self._last_failure_time = now
            # 连续失败 5 次 → OPEN
            if self._failure_count >= 5 and self._state == CircuitState.CLOSED:
                self._state = CircuitState.OPEN
                self._open_at = now
                self._record_audit_event(
                    "CIRCUIT_OPEN",
                    trigger="CONSECUTIVE_FAILURES",
                    failures=self._failure_count,
                    task_id=task_id,
                )
                logger.warning("circuit_opened", failures=self._failure_count)

        # 推送 Prometheus 指标
        self._push_metrics()

    def degrade(self, level: int, context: dict[str, Any] | None = None) -> DegradationResult:
        """执行降级路径。"""
        result = self._degradation.execute(level, context)
        # 统计
        key = result.path
        self._degradation_stats[key] = self._degradation_stats.get(key, 0) + 1
        return result

    def get_state(self) -> ResourceGuardState:
        """返回完整状态快照。"""
        return ResourceGuardState(
            token_bucket_available=self._bucket.available,
            token_bucket_capacity=self._bucket.capacity,
            active_budgets=self._budget.active_count,
            tripped_budgets=self._budget.tripped_count,
            degradation_stats=dict(self._degradation_stats),
        )

    def get_audit_events(self) -> list[dict[str, Any]]:
        """返回所有审计事件。"""
        return list(self._audit_events)

    def set_budget(self, task_id: str, max_tokens: int) -> None:
        """设置任务 Token 预算——委托给 BudgetGuard。"""
        self._budget.set_budget(task_id, max_tokens)

    def reset(self) -> None:
        """完全重置——测试用。"""
        self._bucket.reset()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._open_at = None
        self._half_open_probes = 0
        self._audit_events.clear()
        self._degradation_stats.clear()

    # ── 内部方法 ──────────────────────────────────────────

    def _deny(self, reason: str, level: int) -> GuardResult:
        """构造拒绝结果。"""
        path_map = {1: "L1_BACKUP_MODEL", 2: "L2_RULE_ENGINE", 3: "L3_STALE_CACHE", 4: "L4_HUMAN"}
        return GuardResult(
            decision=GuardDecision.DENY,
            reason=reason,
            degradation_level=level,
            degradation_path=path_map.get(level, ""),
        )

    def _should_enter_half_open(self) -> bool:
        """判断是否可以从 OPEN 进入 HALF_OPEN。

        冷却超时后才允许进入半开探测。
        """
        if self._open_at is None:
            return False
        return (time.time() - self._open_at) >= 60  # 默认冷却 60s

    def _record_audit_event(self, event: str, trigger: str, **kwargs: Any) -> None:
        """记录熔断审计事件。"""
        entry = {
            "event": event,
            "trigger": trigger,
            "timestamp": time.time(),
            **kwargs,
        }
        self._audit_events.append(entry)
        # 环形缓冲: 最多 500 条
        if len(self._audit_events) > 500:
            self._audit_events = self._audit_events[-500:]

    def _push_metrics(self) -> None:
        """推送 Prometheus 指标。"""
        state_map = {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}
        orbit_circuit_breaker_state.labels(breaker="resource_guard").set(
            state_map.get(self._state, 0)
        )
