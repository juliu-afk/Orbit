"""Goal regression guard 单元测试。"""
from orbit.goal.regression_guard import RegressionGuard

def test_init():
    g = RegressionGuard()
    assert g is not None
