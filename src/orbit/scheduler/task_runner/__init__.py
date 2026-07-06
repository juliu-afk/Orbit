"""TaskRunner——单任务生命周期执行器。

拆分为 4 文件: runner.py（核心类+Agent循环）、context.py（上下文构建）、
checkpoint.py（检查点+事件+状态转换）、__init__.py（re-export）。
"""

from orbit.scheduler.task_runner.checkpoint import (
    FAST_LANE_TRANSITIONS,
    InvalidStateTransitionError,
    STATE_TRANSITIONS,
    TERMINAL_STATES,
    _state_to_progress,
    _transition,
)
from orbit.scheduler.task_runner.runner import TaskRunner

__all__ = [
    "TaskRunner",
    "STATE_TRANSITIONS",
    "FAST_LANE_TRANSITIONS",
    "InvalidStateTransitionError",
    "_transition",
    "_state_to_progress",
    "TERMINAL_STATES",
]
