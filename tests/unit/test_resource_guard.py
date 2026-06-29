"""Step 7.3 ResourceGuard 熔断器——单元测试。

覆盖: TokenBucket / BudgetGuard / DegradationPath / ResourceGuard / 性能
"""

import time

import pytest

from orbit.resource_guard.budget_guard import BudgetGuard
from orbit.resource_guard.degradation import DegradationPath
from orbit.resource_guard.models import GuardDecision
from orbit.resource_guard.resource_guard import ResourceGuard
from orbit.resource_guard.token_bucket import TokenBucket

# ── TokenBucket ───────────────────────────────────────────


class TestTokenBucket:
    """令牌桶——创建/消费/补充/拒绝。"""

    def test_allow_within_capacity(self) -> None:
        bucket = TokenBucket(capacity=100, rate=10)
        assert bucket.allow(30) is True
        assert bucket.available < 100  # 已消耗

    def test_allow_exact_available(self) -> None:
        bucket = TokenBucket(capacity=50, rate=10)
        assert bucket.allow(50) is True
        assert bucket.allow(1) is False  # 耗尽

    def test_allow_exceeds_available(self) -> None:
        bucket = TokenBucket(capacity=10, rate=1)
        bucket._tokens = 0  # 强制排空
        assert bucket.allow(5) is False

    def test_refill_over_time(self) -> None:
        bucket = TokenBucket(capacity=100, rate=100)  # 100 tokens/s
        bucket._tokens = 0
        bucket._last_refill = time.monotonic() - 0.5  # 0.5s 前
        # 0.5s * 100/s = 50 tokens refilled
        assert bucket.allow(40) is True

    def test_burst_tolerance(self) -> None:
        """令牌桶允许突发: 满桶时可一次性消耗所有令牌。"""
        bucket = TokenBucket(capacity=5000, rate=100)
        assert bucket.allow(5000) is True  # 突发通过
        assert bucket.allow(1) is False  # 然后被限流

    def test_reset(self) -> None:
        bucket = TokenBucket(capacity=100, rate=10)
        bucket.allow(80)
        bucket.reset()
        assert bucket.available == 100.0


# ── BudgetGuard ───────────────────────────────────────────


class TestBudgetGuard:
    """单任务 Token 预算守卫。"""

    def test_set_and_record_usage(self) -> None:
        guard = BudgetGuard(budget_multiplier=1.5)
        guard.set_budget("task-1", 10000)
        guard.record_usage("task-1", 5000)
        assert guard.is_over_budget("task-1") is False

    def test_over_budget_trips(self) -> None:
        guard = BudgetGuard(budget_multiplier=1.5)
        guard.set_budget("task-1", 1000)
        guard.record_usage("task-1", 1600)  # > 1000*1.5=1500
        assert guard.is_over_budget("task-1") is True

    def test_under_multiplier_no_trip(self) -> None:
        guard = BudgetGuard(budget_multiplier=2.0)
        guard.set_budget("task-1", 1000)
        guard.record_usage("task-1", 1500)  # < 1000*2=2000
        assert guard.is_over_budget("task-1") is False

    def test_task_isolation(self) -> None:
        """一任务超预算不影响其他任务。"""
        guard = BudgetGuard()
        guard.set_budget("t1", 100)
        guard.set_budget("t2", 100)
        guard.record_usage("t1", 999)  # t1 超限
        assert guard.is_over_budget("t1") is True
        assert guard.is_over_budget("t2") is False

    def test_reset_task(self) -> None:
        guard = BudgetGuard()
        guard.set_budget("t1", 100)
        guard.record_usage("t1", 999)
        guard.reset("t1")
        assert guard.is_over_budget("t1") is False
        assert guard.active_count == 0

    def test_get_usage(self) -> None:
        guard = BudgetGuard()
        guard.set_budget("t1", 5000)
        guard.record_usage("t1", 2000)
        info = guard.get_usage("t1")
        assert info["budget"] == 5000
        assert info["used"] == 2000
        assert info["tripped"] is False

    def test_unknown_task_not_over(self) -> None:
        guard = BudgetGuard()
        assert guard.is_over_budget("nonexistent") is False

    def test_tripped_count(self) -> None:
        guard = BudgetGuard()
        guard.set_budget("a", 100)
        guard.set_budget("b", 100)
        guard.record_usage("a", 999)
        assert guard.tripped_count == 1


# ── DegradationPath ───────────────────────────────────────


class TestDegradationPath:
    """4 级降级路径。"""

    def test_l1_backup_model(self) -> None:
        dp = DegradationPath()
        r = dp.execute(1, {"model": "deepseek/deepseek-v4-pro"})
        assert r.path == "L1_BACKUP_MODEL"
        assert r.level == 1
        assert r.data["action"] == "switch_model"
        assert r.data["model"] == "openai/glm-4.7-flash"

    def test_l2_rule_engine(self) -> None:
        dp = DegradationPath()
        r = dp.execute(2, {"error_type": "code_gen"})
        assert r.path == "L2_RULE_ENGINE"
        assert "代码生成" in r.data["message"]

    def test_l3_stale_cache(self) -> None:
        dp = DegradationPath()
        r = dp.execute(3, {"task_id": "t1", "cached_response": "旧数据"})
        assert r.path == "L3_STALE_CACHE"
        assert r.stale is True
        assert r.data["cached_response"] == "旧数据"

    def test_l4_human_escalation(self) -> None:
        dp = DegradationPath()
        r = dp.execute(4, {"task_id": "t1"})
        assert r.path == "L4_HUMAN"
        assert "挂起" in r.data["message"]

    def test_default_to_l4(self) -> None:
        """超出 1-4 范围默认进入 L4。"""
        dp = DegradationPath()
        r = dp.execute(99, {})
        assert r.path == "L4_HUMAN"


# ── ResourceGuard ─────────────────────────────────────────


class TestResourceGuard:
    """ResourceGuard 主入口——组合判断/状态转换/审计。"""

    def test_guard_request_allow(self) -> None:
        guard = ResourceGuard()
        guard.set_budget("t1", 50000)
        r = guard.guard_request("t1", 500)
        assert r.decision == GuardDecision.ALLOW

    def test_guard_token_bucket_empty(self) -> None:
        bucket = TokenBucket(capacity=10, rate=1)
        bucket._tokens = 0
        guard = ResourceGuard(token_bucket=bucket)
        r = guard.guard_request("t1", 50)
        assert r.decision == GuardDecision.DENY
        assert "TOKEN_BUCKET" in r.reason

    def test_guard_task_over_budget(self) -> None:
        guard = ResourceGuard()
        guard.set_budget("t1", 100)
        guard._budget.record_usage("t1", 999)
        r = guard.guard_request("t1", 10)
        assert r.decision == GuardDecision.DENY
        assert "TOKEN_EXCEEDED" in r.reason

    def test_circuit_opens_after_5_failures(self) -> None:
        guard = ResourceGuard()
        for _ in range(5):
            guard.record_result("tx", success=False)
        r = guard.guard_request("tx", 10)
        assert r.decision == GuardDecision.DENY
        # P0 消重: _state→_circuit (GatewayCircuitState)
        assert guard._circuit.opened_at is not None
        assert guard._circuit.half_open is False

    def test_recovery_after_success(self) -> None:
        guard = ResourceGuard()
        # 2 次失败，未达阈值
        guard.record_result("tx", success=False)
        guard.record_result("tx", success=False)
        assert guard._circuit.opened_at is None  # CLOSED
        # 成功恢复
        guard.record_result("tx", success=True)
        assert guard._circuit.failure_count == 0

    def test_audit_event_on_open(self) -> None:
        guard = ResourceGuard()
        for _ in range(5):
            guard.record_result("tx", success=False)
        events = guard.get_audit_events()
        assert len(events) >= 1
        assert events[-1]["event"] == "CIRCUIT_OPEN"
        assert "trigger" in events[-1]

    def test_degradation_stats(self) -> None:
        guard = ResourceGuard()
        guard.degrade(1)
        guard.degrade(2)
        guard.degrade(2)
        state = guard.get_state()
        assert state.degradation_stats.get("L1_BACKUP_MODEL", 0) == 1
        assert state.degradation_stats.get("L2_RULE_ENGINE", 0) == 2

    def test_get_state_snapshot(self) -> None:
        guard = ResourceGuard()
        guard.set_budget("t1", 1000)
        guard.set_budget("t2", 2000)
        guard._budget.record_usage("t2", 9999)
        state = guard.get_state()
        assert state.active_budgets == 2
        assert state.tripped_budgets == 1
        assert state.token_bucket_capacity > 0

    def test_reset(self) -> None:
        guard = ResourceGuard()
        guard.set_budget("t1", 100)
        guard.record_result("t1", success=False)
        guard.degrade(1)
        guard.reset()
        assert guard._circuit.failure_count == 0  # P0 消重: _failure_count→_circuit.failure_count
        assert guard._circuit.opened_at is None
        assert guard._circuit.half_open is False
        assert len(guard.get_audit_events()) == 0
        assert guard.get_state().degradation_stats == {}

    def test_metrics_pushed(self) -> None:
        """验证 Prometheus Gauge 被更新。"""
        from orbit.observability.metrics import orbit_circuit_breaker_state

        guard = ResourceGuard()
        for _ in range(5):
            guard.record_result("tx", success=False)
        val = orbit_circuit_breaker_state.labels(breaker="resource_guard")._value.get()
        assert val == 1.0  # OPEN = 1


# ── 性能基准 ─────────────────────────────────────────────


class TestResourceGuardPerf:
    """SC1: allow_request() P99 <12ms。"""

    def test_allow_request_p99_under_12ms(self) -> None:
        guard = ResourceGuard()
        guard.set_budget("perf-test", 1000000)
        latencies: list[float] = []
        for _ in range(5000):
            start = time.perf_counter()
            guard.guard_request("perf-test", estimated_tokens=100)
            latencies.append((time.perf_counter() - start) * 1000)
        latencies.sort()
        p99_index = int(len(latencies) * 0.99)
        p99 = latencies[p99_index]
        assert p99 < 12, f"P99 latency {p99:.3f}ms exceeds 12ms"

    @pytest.mark.slow
    def test_allow_request_10000(self) -> None:
        """10000 次调用 benchmark。"""
        guard = ResourceGuard()
        guard.set_budget("bench", 1000000)
        start = time.perf_counter()
        for i in range(10000):
            guard.guard_request("bench", estimated_tokens=100)
            guard.record_result("bench", success=i % 10 != 0, tokens_used=50)
        total = time.perf_counter() - start
        # 10000 次应在 12ms * 10000 = 120s 内完成, 实际目标 <<1s
        assert total < 2.0, f"10000 calls took {total:.3f}s"
