from orbit.events.schemas import DashboardEvent
def test_init():
    e = DashboardEvent(type="test", task_id="t1", payload={})
    assert e.type == "test"
