"""Goal module unit test."""
from orbit.goal.ensemble import ModelEnsemble
def test_init():
    i = ModelEnsemble()
    assert i is not None
