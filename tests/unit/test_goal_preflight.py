"""Goal preflight 单元测试。"""
from orbit.goal.preflight import PreFlightEstimator, PreFlightResult

def test_preflight_result_defaults():
    r = PreFlightResult()
    assert r.confidence == 0.5
    assert r.source == "fuzzy"

def test_preflight_result_high_confidence():
    r = PreFlightResult(confidence=0.95, source="exact", token_low=10000)
    assert r.confidence == 0.95
    assert r.source == "exact"

def test_estimator_init():
    e = PreFlightEstimator()
    assert e is not None
