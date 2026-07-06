"""TaskRunner——单任务生命周期执行器。

拆分为 4 文件: runner.py（核心类+Agent循环）、context.py（上下文构建）、
checkpoint.py（检查点+事件）、__init__.py（共享工具函数+状态流转）。
"""

from orbit.api.schemas.task import TaskState
from orbit.scheduler.task_runner.checkpoint import TERMINAL_STATES
from orbit.scheduler.task_runner.runner import TaskRunner

__all__ = ["TaskRunner", "STATE_TRANSITIONS", "FAST_LANE_TRANSITIONS",
           "InvalidStateTransitionError", "_transition", "_state_to_progress"]

# ── 共享工具函数 ────────────────────────────────────────

STATE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.SCOPING,     # Phase 2: PARSING → SCOPING → PLANNING
    TaskState.SCOPING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

FAST_LANE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,       # 快车道跳过 SCOPING+PLANNING
    TaskState.CODING: TaskState.DONE,
    TaskState.DONE: TaskState.DONE,
}


class InvalidStateTransitionError(Exception):
    """非法状态转换.

    P2-9: 不再继承 orchestrator.SchedulerError（避免循环导入）,
    SchedulerError 本身只是 Exception 别名, 功能等价.
    """


def _transition(current: TaskState, fast_lane: bool = False) -> TaskState:
    """执行状态转换（纯函数——从 Scheduler._transition 移出）."""
    if current in TERMINAL_STATES:
        raise InvalidStateTransitionError(f"终态 {current.value} 不可转换")
    transitions = FAST_LANE_TRANSITIONS if fast_lane else STATE_TRANSITIONS
    if current not in transitions:
        raise InvalidStateTransitionError(f"状态 {current.value} 无后继")
    return transitions[current]


def _state_to_progress(state: TaskState) -> float:
    """状态→进度 0.0-1.0."""
    mapping = {
        TaskState.IDLE: 0.0,
        TaskState.PARSING: 0.2,
        TaskState.SCOPING: 0.3,    # Phase 2: PARSING(0.2) < SCOPING(0.3) < PLANNING(0.4)
        TaskState.PLANNING: 0.4,
        TaskState.CODING: 0.7,
        TaskState.VERIFYING: 0.9,
        TaskState.DONE: 1.0,
        TaskState.FAILED: 1.0,
        TaskState.CANCELLED: 1.0,
    }
    return mapping.get(state, 0.0)

# ── 状态流转图 ─────────────────────────────────────────
# IDLE(chatter) → chat intent → DONE
# IDLE(chatter) → programming intent → PARSING(clarifier) → SCOPING(规则引擎)
#   → PLANNING(architect) → CODING(developer) → VERIFYING(reviewer) → DONE
# 快车道: PARSING → CODING → DONE（跳过 SCOPING+PLANNING）
