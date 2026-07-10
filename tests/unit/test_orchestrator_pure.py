"""testing/orchestrator.py pure function tests."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from orbit.testing.orchestrator import TestOrchestrator
from orbit.testing.gate import TestRunResult
from orbit.testing.strategies.intention_driven import GeneratedTest


class TestMergeTestCode:
    def test_merges_imports_and_bodies(self):
        t1 = GeneratedTest(name="t1", code="def test_one(): pass", description="")
        t2 = GeneratedTest(name="t2", code="def test_two(): pass", description="")
        result = TestOrchestrator._merge_test_code([t1, t2])
        assert "import pytest" in result
        assert "test_one" in result


class TestSafeTestName:
    def test_strips_special_chars(self):
        name = TestOrchestrator._safe_test_name("src/svc.py", "API key!")
        assert "svc" in name
        assert "API_key" in name


class TestPushSignal:
    def test_enqueues_signal(self):
        q = asyncio.Queue(maxsize=2)
        TestOrchestrator._push_signal_safe(q, {"a": 1})
        assert q.qsize() == 1

    def test_full_queue_drops_oldest(self):
        q = asyncio.Queue(maxsize=1)
        q.put_nowait({"old": True})
        TestOrchestrator._push_signal_safe(q, {"new": True})
        assert q.qsize() == 1


class TestStaticReview:
    def test_clean_code(self):
        r = TestOrchestrator._static_review_fallback("def add(a,b): return a+b", "m")
        assert len(r["issues"]) == 0

    def test_hardcoded_key(self):
        r = TestOrchestrator._static_review_fallback('api_key = "sk-12345678"', "m")
        assert len(r["issues"]) >= 1

    def test_eval_detected(self):
        r = TestOrchestrator._static_review_fallback("eval(x)", "m")
        assert len(r["issues"]) >= 1

    def test_syntax_error(self):
        r = TestOrchestrator._static_review_fallback("def broken(:", "m")
        assert any(i["severity"] == "blocking" for i in r["issues"])


class TestOrchInit:
    def test_default(self):
        o = TestOrchestrator()
        assert o.max_repair_rounds == 3

    def test_custom_rounds(self):
        o = TestOrchestrator(max_repair_rounds=5)
        assert o.max_repair_rounds == 5


class TestRepairCode:
    def test_no_gateway_returns_original(self):
        o = TestOrchestrator()
        r = TestRunResult(task_id="t", status="failed")
        from orbit.testing.intention import TestIntention
        intent = TestIntention(target="test")
        result = asyncio.run(o._repair_code("code", r, intent))
        assert result == "code"
