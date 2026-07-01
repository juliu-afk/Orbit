"""Goal critique 单元测试。"""
from orbit.goal.critique import CritiqueAgent

def test_init():
    c = CritiqueAgent()
    assert c is not None
