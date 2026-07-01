"""Goal ensemble 单元测试。"""
from orbit.goal.ensemble import ModelEnsemble

def test_execute_returns_result():
    e = ModelEnsemble()
    result = e.execute(task="implement login", context={})
    assert result is not None

def test_init():
    assert ModelEnsemble() is not None
