"""Goal dependency analyzer 单元测试。"""
from orbit.goal.dependency_analyzer import DependencyAnalyzer

def test_init():
    d = DependencyAnalyzer()
    assert d is not None
