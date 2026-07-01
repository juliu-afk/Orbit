from orbit.observability.audit import AuditLogger
def test_init():
    a = AuditLogger(trace_id="test")
    assert a is not None
