"""Goal critique 单元测试。"""
from orbit.goal.critique import CritiqueAgent
from orbit.goal.models import GoalSession

def test_critique_returns_result():
    c = CritiqueAgent()
    goal = GoalSession(description="test")
    result = c.critique(task=goal, code_artifact="def foo(): pass")
    assert result is not None

def test_init():
    assert CritiqueAgent() is not None
