"""Goal progress tracker 单元测试。"""
from orbit.goal.progress_tracker import ProgressTracker
from orbit.goal.models import GoalSession

def test_build_checklist():
    p = ProgressTracker()
    goal = GoalSession(description="implement login")
    items = p.build_checklist(goal=goal)
    assert isinstance(items, list)

def test_update():
    p = ProgressTracker()
    goal = GoalSession(description="test")
    updated = p.update(goal=goal)
    assert updated is not None

def test_init():
    assert ProgressTracker() is not None
