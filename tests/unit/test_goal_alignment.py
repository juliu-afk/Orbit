"""Goal alignment 单元测试。"""
from orbit.goal.alignment import AlignmentCheck

def test_init():
    a = AlignmentCheck()
    assert a is not None
