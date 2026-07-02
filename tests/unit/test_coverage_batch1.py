"""覆盖率补测批次1——compliance + events schemas."""

from __future__ import annotations

import pytest

from orbit.compliance.rule_engine import ComplianceRule, RuleEngine, RuleSeverity
from orbit.compliance.validator import ComplianceResult, ComplianceValidator
from orbit.events.schemas import (
    AgentOpsAlertPayload,
    AlertPayload,
    DashboardEvent,
    MetricsPayload,
    TaskUpdatePayload,
    TokenUpdatePayload,
)


# ════════════════════════════════════════════
# 1. Compliance
# ════════════════════════════════════════════

class TestCompliance:
    def test_rule_severity_enum(self):
        assert RuleSeverity.CRITICAL.value
        assert RuleSeverity.WARNING.value

    def test_rule_creation(self):
        rule = ComplianceRule(
            rule_id="test-001", name="test_rule", description="test",
        )
        assert rule.rule_id == "test-001"

    def test_rule_engine_init(self):
        engine = RuleEngine()
        assert engine is not None

    def test_rule_engine_register(self):
        engine = RuleEngine()
        rule = ComplianceRule(rule_id="custom-001", name="custom", description="custom rule")
        engine.register(rule)
        assert len(engine._rules) >= 1

    def test_validator_init(self):
        v = ComplianceValidator()
        assert v is not None

    def test_compliance_result(self):
        r = ComplianceResult(
            concept="revenue", domain="accounting",
            passed=True, status="pass", rules={},
        )
        assert r.passed is True
        assert r.status == "pass"


# ════════════════════════════════════════════
# 2. Events schemas
# ════════════════════════════════════════════

class TestEventPayloads:
    def test_task_update_payload(self):
        tu = TaskUpdatePayload(
            task_id="t1", state="CODING", progress=0.5,
            dag=[], timestamp="2026-01-01T00:00:00Z",
        )
        assert tu.task_id == "t1"

    def test_token_update_payload(self):
        tu = TokenUpdatePayload(
            task_id="t1", prompt_tokens=1000, completion_tokens=500,
            total_tokens=1500, timestamp="2026-01-01T00:00:00Z",
        )
        assert tu.prompt_tokens == 1000

    def test_alert_payload(self):
        a = AlertPayload(
            task_id="t1", level="l3_entropy", severity="warning",
            message="High entropy detected", timestamp="2026-01-01T00:00:00Z",
        )
        assert a.severity == "warning"

    def test_metrics_payload(self):
        m = MetricsPayload(
            task_id="t1", snapshot={"cpu": 80}, timestamp="2026-01-01T00:00:00Z",
        )
        assert m.snapshot["cpu"] == 80

    def test_agent_ops_alert_payload(self):
        a = AgentOpsAlertPayload(
            task_id="t1", alert_name="agent_timeout",
            severity="warning", message="Agent timed out",
            metrics_snapshot={}, timestamp="2026-01-01T00:00:00Z",
        )
        assert a.alert_name == "agent_timeout"
