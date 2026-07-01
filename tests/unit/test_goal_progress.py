"""Goal progress tracker 单元测试。"""
from orbit.goal.progress_tracker import ProgressTracker

def test_init():
    p = ProgressTracker()
    assert p is not None
