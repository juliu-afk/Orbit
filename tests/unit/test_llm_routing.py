from orbit.gateway.routing import RoutingStrategy
def test_enum():
    assert RoutingStrategy.CHEAPEST.value == "cheapest"
