from orbit.goal.preflight import PreFlightEstimator, PreFlightResult
def test_result():
    r = PreFlightResult()
    assert r.confidence == 0.5
    assert r.source == "fuzzy"
def test_estimator():
    assert PreFlightEstimator() is not None
