"""Goal ensemble 单元测试。"""
from orbit.goal.ensemble import ModelEnsemble

def test_init():
    e = ModelEnsemble()
    assert e is not None
