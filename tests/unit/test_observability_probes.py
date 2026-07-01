from orbit.observability.probes import StartupProbeEngine
def test_init():
    e = StartupProbeEngine()
    assert e is not None
