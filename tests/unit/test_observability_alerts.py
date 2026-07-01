from orbit.observability.alerts import AlertEngine
def test_init():
    e = AlertEngine()
    assert e is not None
