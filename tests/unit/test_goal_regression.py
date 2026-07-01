"""Goal regression guard 单元测试。"""
from orbit.goal.regression_guard import RegressionGuard

def test_check_returns_result():
    g = RegressionGuard()
    result = g.check()
    assert result is not None

def test_init():
    assert RegressionGuard() is not None
