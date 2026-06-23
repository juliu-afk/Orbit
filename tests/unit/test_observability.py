"""Step 7.2 HealthCollector 单元测试。"""

import pytest

from orbit.observability.collector import (
    ComponentStatus,
    HealthCollector,
)


class TestHealthCollector:
    """健康指标聚合器——注册/更新/汇总/摘要。"""

    @pytest.fixture
    def collector(self) -> HealthCollector:
        return HealthCollector()

    def test_register(self, collector: HealthCollector) -> None:
        collector.register("scheduler")
        h = collector.get("scheduler")
        assert h is not None
        assert h.status == ComponentStatus.UNKNOWN

    def test_update_status(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, "OK")
        h = collector.get("test")
        assert h is not None
        assert h.status == ComponentStatus.HEALTHY
        assert h.message == "OK"

    def test_update_metrics(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, metrics={"latency_ms": 5})
        h = collector.get("test")
        assert h is not None
        assert h.metrics["latency_ms"] == 5

    def test_overall_all_healthy(self, collector: HealthCollector) -> None:
        for name in ["a", "b"]:
            collector.register(name)
            collector.update(name, ComponentStatus.HEALTHY)
        assert collector.overall_status() == ComponentStatus.HEALTHY

    def test_overall_one_degraded(self, collector: HealthCollector) -> None:
        collector.register("a")
        collector.update("a", ComponentStatus.HEALTHY)
        collector.register("b")
        collector.update("b", ComponentStatus.DEGRADED)
        assert collector.overall_status() == ComponentStatus.DEGRADED

    def test_overall_one_unhealthy(self, collector: HealthCollector) -> None:
        collector.register("a")
        collector.update("a", ComponentStatus.HEALTHY)
        collector.register("b")
        collector.update("b", ComponentStatus.UNHEALTHY)
        assert collector.overall_status() == ComponentStatus.UNHEALTHY

    def test_overall_empty(self, collector: HealthCollector) -> None:
        assert collector.overall_status() == ComponentStatus.UNKNOWN

    def test_summary_format(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, "ok", {"key": 1})
        s = collector.summary()
        assert s["overall"] == "healthy"
        assert len(s["components"]) == 1
        assert s["components"][0]["metrics"]["key"] == 1

    def test_list_all(self, collector: HealthCollector) -> None:
        for name in ["x", "y", "z"]:
            collector.register(name)
        assert len(collector.list_all()) == 3


# ── Step 7.2 扩展：Prometheus 业务指标 ─────────────────────


class TestMetrics:
    """Prometheus 业务指标——创建/递增/快照。"""

    def test_tasks_counter_increments(self) -> None:
        from orbit.observability.metrics import orbit_tasks_total, snapshot

        orbit_tasks_total.labels(status="success").inc()
        orbit_tasks_total.labels(status="failed").inc()
        orbit_tasks_total.labels(status="failed").inc()
        snap = snapshot()
        assert snap["tasks_total"]["success"] == 1.0
        assert snap["tasks_total"]["failed"] == 2.0

    def test_active_tasks_gauge(self) -> None:
        from orbit.observability.metrics import orbit_active_tasks, snapshot

        orbit_active_tasks.set(5)
        snap = snapshot()
        assert snap["active_tasks"] == 5.0
        orbit_active_tasks.set(0)

    def test_llm_tokens_counter(self) -> None:
        from orbit.observability.metrics import orbit_llm_tokens_total, snapshot

        orbit_llm_tokens_total.labels(type="input").inc(100)
        orbit_llm_tokens_total.labels(type="output").inc(50)
        snap = snapshot()
        assert snap["llm_tokens_total"]["input"] == 100.0
        assert snap["llm_tokens_total"]["output"] == 50.0

    def test_hallucination_intercepted(self) -> None:
        from orbit.observability.metrics import (
            orbit_hallucination_intercepted_total,
            snapshot,
        )

        orbit_hallucination_intercepted_total.labels(layer="L1").inc()
        orbit_hallucination_intercepted_total.labels(layer="L3").inc()
        orbit_hallucination_intercepted_total.labels(layer="L3").inc()
        snap = snapshot()
        assert snap["hallucination_intercepted_total"]["L1"] == 1.0
        assert snap["hallucination_intercepted_total"]["L3"] == 2.0
        # 未触发的层应为 0
        assert snap["hallucination_intercepted_total"]["L2"] == 0.0

    def test_circuit_breaker_state(self) -> None:
        from orbit.observability.metrics import orbit_circuit_breaker_state, snapshot

        orbit_circuit_breaker_state.labels(breaker="z3").set(1)
        orbit_circuit_breaker_state.labels(breaker="llm").set(0)
        snap = snapshot()
        assert snap["circuit_breaker_state"]["z3"] == 1.0
        assert snap["circuit_breaker_state"]["llm"] == 0.0

    def test_sandbox_metrics(self) -> None:
        from orbit.observability.metrics import (
            orbit_sandbox_executions_total,
            orbit_sandbox_pool_available,
            snapshot,
        )

        orbit_sandbox_pool_available.set(3)
        orbit_sandbox_executions_total.labels(result="success").inc(10)
        orbit_sandbox_executions_total.labels(result="failed").inc(2)
        snap = snapshot()
        assert snap["sandbox_pool_available"] == 3.0
        assert snap["sandbox_executions_total"]["success"] == 10.0
        assert snap["sandbox_executions_total"]["failed"] == 2.0

    def test_compliance_checks(self) -> None:
        from orbit.observability.metrics import orbit_compliance_checks_total, snapshot

        orbit_compliance_checks_total.labels(status="pass").inc(5)
        orbit_compliance_checks_total.labels(status="violation").inc(1)
        snap = snapshot()
        assert snap["compliance_checks_total"]["pass"] == 5.0
        assert snap["compliance_checks_total"]["violation"] == 1.0

    def test_snapshot_covers_all_keys(self) -> None:
        from orbit.observability.metrics import snapshot

        snap = snapshot()
        expected_keys = [
            "tasks_total",
            "active_tasks",
            "llm_tokens_total",
            "hallucination_intercepted_total",
            "circuit_breaker_state",
            "sandbox_pool_available",
            "sandbox_executions_total",
            "compliance_checks_total",
        ]
        for key in expected_keys:
            assert key in snap, f"Missing key: {key}"


# ── Step 7.2 扩展：审计日志 + 教训库 ─────────────────────


class TestAuditLogger:
    """审计日志记录器——structlog 封装。"""

    def test_audit_log_emits(self) -> None:
        from orbit.observability.audit import AuditLogger

        audit = AuditLogger(trace_id="trace-001")
        # 不抛异常即为通过
        audit.log("scheduler", "task_start", task_id="task-001", status="success")
        audit.log("llm_gateway", "llm_call", task_id="task-001", tokens=35)

    def test_audit_log_disabled(self) -> None:
        from orbit.observability.audit import AuditLogger

        audit = AuditLogger()
        # 禁用时不抛异常
        audit.log("test", "op", task_id="t1")


class TestLessonStore:
    """教训库——SQLite 存储 CRUD。"""

    def test_add_and_count(self) -> None:
        from orbit.observability.audit import LessonStore

        store = LessonStore()
        try:
            store.add("task-001", "scheduler", "failure", "DAG timeout", ["timeout"])
            store.add("task-002", "llm", "success", "Good prompt engineering")
            assert store.count() == 2
        finally:
            store.close()
            _cleanup_lesson_db()

    def test_list_by_domain(self) -> None:
        from orbit.observability.audit import LessonStore

        store = LessonStore()
        try:
            store.add("t1", "scheduler", "failure", "err1")
            store.add("t2", "scheduler", "success", "ok1")
            store.add("t3", "llm", "failure", "err2")
            results = store.list_by_domain("scheduler")
            assert len(results) == 2
            assert all(r.domain == "scheduler" for r in results)
        finally:
            store.close()
            _cleanup_lesson_db()

    def test_list_by_task(self) -> None:
        from orbit.observability.audit import LessonStore

        store = LessonStore()
        try:
            store.add("task-001", "scheduler", "failure", "err")
            store.add("task-002", "llm", "success", "ok")
            results = store.list_by_task("task-001")
            assert len(results) == 1
            assert results[0].task_id == "task-001"
            assert results[0].outcome == "failure"
        finally:
            store.close()
            _cleanup_lesson_db()

    def test_tags_parsing(self) -> None:
        from orbit.observability.audit import LessonStore

        store = LessonStore()
        try:
            store.add("t1", "sandbox", "failure", "timeout", ["timeout", "docker"])
            results = store.list_by_task("t1")
            assert len(results) == 1
            assert "timeout" in results[0].tags
            assert "docker" in results[0].tags
        finally:
            store.close()
            _cleanup_lesson_db()


# ── Step 7.2 扩展：告警规则引擎 ──────────────────────────


class TestAlertEngine:
    """告警规则引擎——注册/评估/冷却/活跃/历史。"""

    def test_register_and_evaluate_no_hit(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="test_rule",
                description="测试规则",
                severity=AlertSeverity.WARNING,
                condition=lambda m: m.get("value", 0) > 100,
            )
        )
        alerts = engine.evaluate({"value": 50})
        assert len(alerts) == 0

    def test_register_and_evaluate_hit(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="test_rule",
                description="测试",
                severity=AlertSeverity.CRITICAL,
                condition=lambda m: m.get("value", 0) > 100,
            )
        )
        alerts = engine.evaluate({"value": 200})
        assert len(alerts) == 1
        assert alerts[0].name == "test_rule"
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_cooldown_prevents_retrigger(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="cooldown_test",
                description="冷却测试",
                severity=AlertSeverity.WARNING,
                condition=lambda m: True,  # 始终触发
                cooldown_seconds=3600,  # 1 小时冷却
            )
        )
        # 第一次触发
        a1 = engine.evaluate({})
        assert len(a1) == 1
        # 冷却期内不应再触发
        a2 = engine.evaluate({})
        assert len(a2) == 0

    def test_get_active_during_cooldown(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="active_test",
                description="活跃测试",
                severity=AlertSeverity.WARNING,
                condition=lambda m: True,
                cooldown_seconds=3600,
            )
        )
        engine.evaluate({})
        active = engine.get_active()
        assert len(active) == 1
        assert active[0]["name"] == "active_test"

    def test_get_history(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="hist_test",
                description="历史测试",
                severity=AlertSeverity.WARNING,
                condition=lambda m: True,
                cooldown_seconds=0,  # 无冷却，每次都触发
            )
        )
        engine.evaluate({})
        engine.evaluate({})
        engine.evaluate({})
        history = engine.get_history(limit=2)
        assert len(history) == 2

    def test_builtin_rules_load(self) -> None:
        from orbit.observability.alerts import AlertEngine

        engine = AlertEngine()
        engine.add_builtin_rules()
        assert len(engine._rules) == 5
        assert "high_token_consumption" in engine._rules
        assert "high_entropy" in engine._rules
        assert "sandbox_pool_exhausted" in engine._rules
        assert "config_drift" in engine._rules
        assert "circuit_breaker_open" in engine._rules

    def test_condition_eval_error_handled(self) -> None:
        from orbit.observability.alerts import AlertEngine, AlertRule, AlertSeverity

        engine = AlertEngine()
        engine.register(
            AlertRule(
                name="broken_rule",
                description="会抛异常的规则",
                severity=AlertSeverity.WARNING,
                condition=lambda m: m["nonexistent_key"] > 0,  # KeyError
            )
        )
        # 不应抛异常，返回空列表
        alerts = engine.evaluate({})
        assert len(alerts) == 0


# ── Step 7.2 扩展：AgentOpsConfig ────────────────────────


class TestAgentOpsConfig:
    """AgentOps 配置——默认值/环境变量覆盖。"""

    def test_defaults(self) -> None:
        from orbit.observability.config import AgentOpsConfig

        cfg = AgentOpsConfig()
        assert cfg.TOKEN_THRESHOLD_WARNING == 50
        assert cfg.TOKEN_THRESHOLD_CRITICAL == 100
        assert cfg.Z3_TIMEOUT_RATE_THRESHOLD == 5.0
        assert cfg.ENTROPY_BITS_THRESHOLD == 2.5
        assert cfg.ALERT_COOLDOWN_SECONDS == 300
        assert cfg.AUDIT_LOG_ENABLED is True
        assert cfg.LESSON_STORE_ENABLED is True
        assert cfg.AUTO_FIX_ENABLED is False

    def test_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTOPS_TOKEN_THRESHOLD_WARNING", "80")
        monkeypatch.setenv("AGENTOPS_AUTO_FIX_ENABLED", "true")

        # config 在 import 时读取环境变量，需重载模块
        import importlib

        import orbit.observability.config

        importlib.reload(orbit.observability.config)
        from orbit.observability.config import AgentOpsConfig

        cfg = AgentOpsConfig()
        assert cfg.TOKEN_THRESHOLD_WARNING == 80
        assert cfg.AUTO_FIX_ENABLED is True

        # 恢复默认值
        monkeypatch.delenv("AGENTOPS_TOKEN_THRESHOLD_WARNING")
        monkeypatch.delenv("AGENTOPS_AUTO_FIX_ENABLED")
        importlib.reload(orbit.observability.config)


# ── 辅助函数 ─────────────────────────────────────────────


def _cleanup_lesson_db() -> None:
    import os

    if os.path.exists("data/lessons.db"):
        os.remove("data/lessons.db")
