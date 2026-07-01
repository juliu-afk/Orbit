"""Goal verifier 单元测试。"""
from orbit.goal.verifier import ExecutorVerifier

def test_init():
    v = ExecutorVerifier()
    assert v is not None
