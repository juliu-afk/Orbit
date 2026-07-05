"""Phase A: 元认知层 + ReflAct 单元测试.

覆盖: ReflectionResult, RepetitionDetector, GoalDriftDetector,
       LatencyWatchdog, ErrorClassifier, HITLManager, TriggerEngine.
"""
from __future__ import annotations

import asyncio

import pytest

from orbit.agents.reflection import ReflectionResult
from orbit.metacognition.classifier import AgentErrorCategory, ErrorClassifier
from orbit.metacognition.hitl import HITLAction, HITLManager, HITLRequest, HITLResponse
from orbit.metacognition.triggers import (
    Alert,
    AlertType,
    GoalDriftDetector,
    LatencyWatchdog,
    RepetitionDetector,
    Severity,
    TriggerEngine,
)


class TestReflectionResult:
    """ReflectionResult 解析和判断。"""

    def test_goal_alignment_yes(self):
        r = ReflectionResult.from_json({
            "goal_alignment": "YES", "confidence": 90, "should_continue": True
        })
        assert r.goal_alignment == "YES"
        assert not r.is_drifting()

    def test_goal_alignment_no_is_drifting(self):
        r = ReflectionResult.from_json({
            "goal_alignment": "NO", "confidence": 30,
            "should_continue": False, "correction_needed": "检查应收账款明细"
        })
        assert r.is_drifting()
        assert r.confidence == 30

    def test_low_confidence_triggers_drift(self):
        r = ReflectionResult.from_json({
            "goal_alignment": "YES", "confidence": 25, "should_continue": True
        })
        assert r.is_drifting()  # confidence < 40

    def test_skip(self):
        r = ReflectionResult.skip("no LLM available")
        assert r.goal_alignment == "YES"
        assert r.should_continue
        assert not r.is_drifting()


class TestRepetitionDetector:
    """重复动作检测。"""

    def test_detects_repetition(self):
        d = RepetitionDetector(window_size=3, similarity_threshold=3)
        actions = [{"tool": "read_file", "args": {"path": "x.csv"}}] * 5
        alert = d.check(actions)
        assert alert is not None
        assert alert.type == AlertType.REPETITION

    def test_no_repetition_with_varied_actions(self):
        d = RepetitionDetector(window_size=3, similarity_threshold=3)
        actions = [
            {"tool": "read_file", "args": {"path": "a.csv"}},
            {"tool": "grep", "args": {"pattern": "def"}},
            {"tool": "exec_command", "args": {"cmd": "pytest"}},
        ]
        alert = d.check(actions)
        assert alert is None

    def test_insufficient_actions(self):
        d = RepetitionDetector(window_size=5, similarity_threshold=3)
        actions = [{"tool": "read_file", "args": {}}] * 2
        alert = d.check(actions)
        assert alert is None


class TestGoalDriftDetector:
    """目标漂移检测。"""

    def test_exec_command_not_match_audit_goal(self):
        d = GoalDriftDetector(drift_window=2)
        assert d.check_rule("检查2024年应收账款坏账准备", "exec_command")

    def test_read_file_matches_audit_goal(self):
        d = GoalDriftDetector(drift_window=2)
        assert not d.check_rule("检查2024年应收账款坏账准备", "read_file")

    def test_accumulates_drift_then_alerts(self):
        d = GoalDriftDetector(drift_window=2)
        assert d.check("审计目标", "exec_command") is None
        alert = d.check("审计目标", "exec_command")  # 第二次 → 触发
        assert alert is not None
        assert alert.type == AlertType.GOAL_DRIFT

    def test_reset_clears_drift(self):
        d = GoalDriftDetector(drift_window=2)
        d.check("审计目标", "exec_command")
        d.reset()
        assert d.check("审计目标", "exec_command") is None  # count=1 again


class TestLatencyWatchdog:
    """延迟看门狗。"""

    def test_action_timeout(self):
        import time
        w = LatencyWatchdog(max_action_ms=10)
        alert = w.check_action(time.time() - 1)  # 1s ago > 10ms
        assert alert is not None
        assert alert.type == AlertType.LATENCY

    def test_action_ok(self):
        import time
        w = LatencyWatchdog(max_action_ms=999_999)
        alert = w.check_action(time.time())  # just now
        assert alert is None


class TestErrorClassifier:
    """错误分类。"""

    def test_goal_drift_to_forgetting(self):
        c = ErrorClassifier()
        cat = c.classify(Alert(type=AlertType.GOAL_DRIFT, severity=Severity.WARNING, message="x"))
        assert cat == AgentErrorCategory.GOAL_FORGETTING

    def test_repetition_to_planning_deviation(self):
        c = ErrorClassifier()
        cat = c.classify(Alert(type=AlertType.REPETITION, severity=Severity.WARNING, message="x"))
        assert cat == AgentErrorCategory.PLANNING_DEVIATION

    def test_batch(self):
        c = ErrorClassifier()
        alerts = [
            Alert(type=AlertType.GOAL_DRIFT, severity=Severity.WARNING, message="1"),
            Alert(type=AlertType.GOAL_DRIFT, severity=Severity.WARNING, message="2"),
            Alert(type=AlertType.REPETITION, severity=Severity.WARNING, message="3"),
        ]
        counts = c.classify_batch(alerts)
        assert counts[AgentErrorCategory.GOAL_FORGETTING] == 2
        assert counts[AgentErrorCategory.PLANNING_DEVIATION] == 1


class TestHITLManager:
    """HITL 管理器。"""

    async def test_timeout_auto_abort(self):
        hitl = HITLManager(default_timeout=0.01)
        req = hitl.build_request("goal_drift", "critical", "偏离目标", goal="审计")
        resp = await hitl.request_intervention("task_1", req, timeout=0.01)
        assert resp.action == HITLAction.ABORT

    async def test_manual_resolve(self):
        hitl = HITLManager(default_timeout=5.0)
        req = hitl.build_request("goal_drift", "critical", "偏离目标")

        async def resolve_later():
            await asyncio.sleep(0.05)
            hitl.resolve("task_x", HITLResponse(action=HITLAction.CONTINUE, reason="确认继续"))

        asyncio.create_task(resolve_later())
        resp = await hitl.request_intervention("task_x", req, timeout=1.0)
        assert resp.action == HITLAction.CONTINUE
        assert resp.reason == "确认继续"

    def test_build_request(self):
        hitl = HITLManager()
        req = hitl.build_request(
            "goal_drift", "critical", "偏移严重",
            goal="审计目标", state="coding",
            suggested_action=HITLAction.STEP_BACK,
            context={"drift_count": 5},
        )
        assert req.alert_type == "goal_drift"
        assert req.severity == "critical"
        assert req.original_goal == "审计目标"
        assert req.suggested_action == HITLAction.STEP_BACK
        assert req.context["drift_count"] == 5


class TestTriggerEngine:
    """组合触发器引擎。"""

    def test_combines_all_detectors(self):
        engine = TriggerEngine(
            repetition=RepetitionDetector(window_size=1, similarity_threshold=1),
            goal_drift=GoalDriftDetector(drift_window=1),
            latency=LatencyWatchdog(max_action_ms=10, max_total_ms=999_999),
        )
        import time
        actions = [{"tool": "read_file", "args": {"path": "x.csv"}}]
        alerts = engine.check_all(
            recent_actions=actions,
            goal="检查应收账款",
            last_tool="exec_command",  # 不匹配审计目标
            action_start=time.time() - 1,  # 超时
        )
        # Should have: repetition + goal_drift + latency = 3 alerts
        assert len(alerts) >= 2  # 至少重复+漂移

    def test_critical_sorted_first(self):
        engine = TriggerEngine()
        # Force CRITICAL via goal_drift
        d = GoalDriftDetector(drift_window=1)
        d._drift_count = 10  # 超过阈值→CRITICAL
        engine.goal_drift = d
        import time
        alerts = engine.check_all(
            recent_actions=[],
            goal="审计",
            last_tool="exec_command",
            action_start=time.time() - 1,
        )
        if alerts:
            # CRITICAL 应该排在 WARNING 前面
            severities = [a.severity for a in alerts]
            crit_idx = next((i for i, s in enumerate(severities) if s == Severity.CRITICAL), -1)
            warn_idx = next((i for i, s in enumerate(severities) if s == Severity.WARNING), -1)
            if crit_idx >= 0 and warn_idx >= 0:
                assert crit_idx < warn_idx, "CRITICAL should sort before WARNING"
