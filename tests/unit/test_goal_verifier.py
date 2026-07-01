"""Goal verifier 单元测试。"""
from orbit.goal.verifier import ExecutorVerifier, VerificationResult

def test_verification_result_defaults():
    r = VerificationResult()
    assert r.all_passed is True
    assert r.results == []

def test_verification_result_failed():
    r = VerificationResult(all_passed=False, results=[{"name":"test1","passed":False}])
    assert r.all_passed is False
    assert len(r.results) == 1

def test_verifier_init():
    v = ExecutorVerifier()
    assert v is not None
