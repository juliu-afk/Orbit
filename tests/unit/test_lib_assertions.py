"""测试库自身测试——assertions/ 模块。

验证所有专用断言：状态转换/检查点/防幻觉/熔断/沙箱。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.gateway import assert_circuit_state, assert_fallback_triggered
from tests.lib.assertions.hallucination import assert_layer_blocked, assert_layer_passed
from tests.lib.assertions.sandbox import assert_execution_isolated
from tests.lib.assertions.task import (
    assert_checkpoint_saved,
    assert_event_published,
    assert_state_transition,
)
from tests.lib.mocks import MockCircuitBreaker


# ── Task 断言 ───────────────────────────────────────────

class TestTaskAssertions:
    def test_assert_state_transition_ok(self):
        history = ["IDLE", "PARSING", "PLANNING", "CODING", "DONE"]
        assert_state_transition(history, "IDLE", "PARSING")
        assert_state_transition(history, "CODING", "DONE")

    def test_assert_state_transition_missing(self):
        history = ["IDLE", "CODING", "DONE"]
        with pytest.raises(AssertionError):
            assert_state_transition(history, "IDLE", "PARSING")

    def test_assert_state_transition_empty(self):
        with pytest.raises(AssertionError):
            assert_state_transition([], "IDLE", "DONE")

    def test_assert_checkpoint_saved(self):
        checkpoints = [
            {"state": "IDLE"}, {"state": "PARSING"}, {"state": "CODING"}
        ]
        assert_checkpoint_saved(checkpoints, "CODING")

    def test_assert_checkpoint_missing(self):
        checkpoints = [{"state": "IDLE"}]
        with pytest.raises(AssertionError):
            assert_checkpoint_saved(checkpoints, "DONE")

    def test_assert_event_published(self):
        events = [
            {"type": "task:update"}, {"type": "dag:complete"}, {"type": "task:done"}
        ]
        assert_event_published(events, "task:update")

    def test_assert_event_not_published(self):
        events = [{"type": "noise"}]
        with pytest.raises(AssertionError):
            assert_event_published(events, "task:update")


# ── 防幻觉 断言 ─────────────────────────────────────────

class TestHallucinationAssertions:
    def test_assert_layer_passed(self):
        result = {"layers": {"L1": True, "L3": True}}
        assert_layer_passed(result, "L1")
        assert_layer_passed(result, "L3")

    def test_assert_layer_passed_fails(self):
        result = {"layers": {"L1": False}}
        with pytest.raises(AssertionError):
            assert_layer_passed(result, "L1")

    def test_assert_layer_blocked(self):
        result = {"layers": {"L3": False}, "reasons": {"L3": "Entropy 0.89 exceeds threshold 0.75"}}
        assert_layer_blocked(result, "L3", reason_contains="Entropy")

    def test_assert_layer_blocked_fails_if_passed(self):
        result = {"layers": {"L3": True}, "reasons": {}}
        with pytest.raises(AssertionError):
            assert_layer_blocked(result, "L3")

    def test_assert_layer_blocked_wrong_reason(self):
        result = {"layers": {"L3": False}, "reasons": {"L3": "Entropy too high"}}
        with pytest.raises(AssertionError):
            assert_layer_blocked(result, "L3", reason_contains="NonexistentPattern")


# ── Gateway 断言 ────────────────────────────────────────

class TestGatewayAssertions:
    def test_assert_circuit_state_closed(self):
        cb = MockCircuitBreaker(state="CLOSED")
        assert_circuit_state(cb, "CLOSED")

    def test_assert_circuit_state_open(self):
        cb = MockCircuitBreaker(state="OPEN")
        assert_circuit_state(cb, "OPEN")

    def test_assert_circuit_state_wrong(self):
        cb = MockCircuitBreaker(state="CLOSED")
        with pytest.raises(AssertionError):
            assert_circuit_state(cb, "OPEN")

    def test_assert_fallback_triggered(self):
        from tests.lib.factories.llm import create_llm_response

        responses = [
            create_llm_response(model="deepseek-v4-pro", degraded=False),
            create_llm_response(model="glm-4.7-flash", degraded=True),
        ]
        assert_fallback_triggered(responses, "deepseek-v4-pro", "glm-4.7-flash")

    def test_assert_fallback_not_triggered(self):
        from tests.lib.factories.llm import create_llm_response

        responses = [
            create_llm_response(model="deepseek-v4-pro", degraded=False),
        ]
        with pytest.raises(AssertionError):
            assert_fallback_triggered(responses, "deepseek-v4-pro", "glm-4.7-flash")


# ── Sandbox 断言 ────────────────────────────────────────

class TestSandboxAssertions:
    def test_assert_isolated_dict(self):
        assert_execution_isolated({"exit_code": 0, "stdout": "OK"})

    def test_assert_isolated_tuple(self):
        assert_execution_isolated((0, "OK", ""))

    def test_assert_isolated_str(self):
        assert_execution_isolated("OK")

    def test_assert_isolated_nonzero_exit(self):
        with pytest.raises(AssertionError):
            assert_execution_isolated({"exit_code": 1, "stdout": "FAIL"})

    def test_assert_isolated_invalid_type(self):
        with pytest.raises(AssertionError):
            assert_execution_isolated(None)
