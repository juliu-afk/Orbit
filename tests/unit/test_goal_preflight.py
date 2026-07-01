"""Goal preflight 单元测试。"""
from orbit.goal.preflight import PreFlightEstimator

def test_init():
    p = PreFlightEstimator()
    assert p is not None
