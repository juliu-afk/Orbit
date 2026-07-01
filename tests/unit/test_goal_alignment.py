"""Goal alignment 单元测试。"""
from orbit.goal.alignment import AlignmentCheck

def test_check_returns_result():
    a = AlignmentCheck()
    result = a.check(goal="implement login", progress={})
    assert result is not None

def test_init():
    assert AlignmentCheck() is not None
