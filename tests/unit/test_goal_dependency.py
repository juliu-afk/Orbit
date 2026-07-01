"""Goal dependency analyzer 单元测试。"""
from orbit.goal.dependency_analyzer import DependencyAnalyzer
from orbit.goal.models import GoalSession

def test_analyze_returns_result():
    d = DependencyAnalyzer()
    goals = [GoalSession(description="task1"), GoalSession(description="task2")]
    result = d.analyze(goals=goals)
    assert result is not None

def test_init():
    assert DependencyAnalyzer() is not None
