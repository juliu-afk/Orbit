import asyncio
from unittest.mock import MagicMock
import pytest
from orbit.testing.orchestrator import TestOrchestrator
from orbit.testing.gate import TestRunResult

class TestMergeTestCode:
    def test_merges(self):
        from orbit.testing.strategies.intention_driven import GeneratedTest
        t1 = GeneratedTest(name="t1", code="def test_one(): pass", description="", framework_fit=None)
        t2 = GeneratedTest(name="t2", code="def test_two(): pass", description="", framework_fit=None)
        result = TestOrchestrator._merge_test_code([t1, t2])
        assert "import pytest" in result
        assert "test_one" in result

class TestSafeTestName:
    def test_strips(self):
        name = TestOrchestrator._safe_test_name("src/svc.py", "API key!")
        assert "svc" in name

class TestPushSignal:
    def test_enqueues(self):
        q = asyncio.Queue(maxsize=2)
        TestOrchestrator._push_signal_safe(q, {"a": 1})
        assert q.qsize() == 1

class TestStaticReview:
    def test_key(self):
        r = TestOrchestrator._static_review_fallback('api_key="sk-12345678"', "m", "g1")
        assert len(r["issues"]) >= 1
    def test_eval(self):
        r = TestOrchestrator._static_review_fallback("eval(x)", "m", "g1")
        assert len(r["issues"]) >= 1

class TestOrchInit:
    def test_default(self):
        o = TestOrchestrator()
        assert o.max_repair_rounds == 3

class TestRepairCode:
    def test_no_gateway(self):
        o = TestOrchestrator()
        r = TestRunResult(task_id="t", status="failed")
        from orbit.testing.intention import TestIntention
        intent = TestIntention(target="test")
        result = asyncio.run(o._repair_code("code", r, intent))
        assert result == "code"
