"""流程强制守卫——代码级状态转换检查。

对标 MetaGPT SOP enforcement: 违反 SOP → 拒绝传递产物。
LLM 不可绕过——ProcessViolationError 阻断执行。

WHY 代码级而非 prompt 级: MetaGPT 研究证明 prompt-only 约束
可被 LLM 通过 prompt 注入绕过。代码级守卫不可绕过。

状态机: IDLE → PARSING → PLANNING → CODING → CRITIQUE_GATE → VERIFYING → DONE
强制状态: PARSING + CODING ——任何情况下不可跳过
可跳过状态: PLANNING + VERIFYING ——仅 ComplexityScorer 可授权快车道
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.api.schemas.task import TaskState

logger = structlog.get_logger("orbit.goal")

# 状态序号——用于正确排序比较（StrEnum 的字符串排序不等于流水线顺序）
_STATE_ORDER: dict[TaskState, int] = {
    TaskState.IDLE: 0,
    TaskState.PARSING: 1,
    TaskState.PLANNING: 2,
    TaskState.CODING: 3,
    TaskState.VERIFYING: 4,
    TaskState.DONE: 5,
    TaskState.FAILED: 10,
    TaskState.CANCELLED: 10,
}


class ProcessViolationError(Exception):
    """流程违规——LLM 尝试跳过强制状态时抛出。

    对标 MetaGPT: SOP violation → refuse to forward artifact。
    """

    def __init__(self, task_id: str, from_state: str, to_state: str, reason: str) -> None:
        self.task_id = task_id
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f"流程违规: task={task_id} {from_state}→{to_state}: {reason}")


# 完整流水线状态转换表
FULL_PIPELINE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

# 快车道路径——跳过 PLANNING + VERIFYING（仅 ComplexityScorer 可授权）
FAST_LANE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,  # 跳过 PLANNING
    TaskState.CODING: TaskState.DONE,  # 跳过 VERIFYING
    TaskState.DONE: TaskState.DONE,
}

TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.DONE,
        TaskState.FAILED,
        TaskState.CANCELLED,
    }
)


class ProcessGuard:
    """状态转换守卫——确保每个子任务走完完整流水线。

    不可绕过的强制状态: PARSING, CODING
    仅 ComplexityScorer 可授权跳过的状态: PLANNING, VERIFYING
    CRITIQUE_GATE 不是独立状态——是 CODING→VERIFYING 转换时的门禁（由 CritiqueAgent 执行）
    """

    # 任何情况下不可跳过的状态
    MANDATORY_STATES: frozenset[TaskState] = frozenset(
        {
            TaskState.PARSING,
            TaskState.CODING,
        }
    )

    # 快车道可跳过的状态——仅 ComplexityScorer 可授权
    FAST_LANE_SKIPPABLE: frozenset[TaskState] = frozenset(
        {
            TaskState.PLANNING,
            TaskState.VERIFYING,
        }
    )

    def __init__(self, task_id: str, goal_id: str) -> None:
        self.task_id = task_id
        self.goal_id = goal_id
        self._visited: set[TaskState] = set()
        self._fast_lane = False  # 仅 ComplexityScorer 可设置——LLM 不可调用

    # ── 公共 API ──────────────────────────────────────

    def authorize_fast_lane(self, scorer_result: dict | None = None) -> None:
        """授权快车道——仅 ComplexityScorer 可调用。

        快车道跳过 PLANNING 和 VERIFYING。
        LLM 无权调用此方法——code-level enforcement。

        WHY 独立方法: 调用方显式声明"我知道我在授权快车道"，
        不会被 LLM 通过函数调用误触发。
        """
        if scorer_result is None:
            return
        if scorer_result.get("recommended_mode") == "fast":
            self._fast_lane = True
            logger.info(
                "process_guard_fast_lane_authorized",
                task_id=self.task_id,
            )

    async def check(
        self,
        current_state: TaskState,
        context: dict[str, Any],
    ) -> None:
        """在每次状态转换前检查流程合规性。

        检查项:
        1. 上一状态是否已完成（有 artifact）
        2. 是否跳过了强制状态
        3. 快车道跳过是否经 ComplexityScorer 授权

        Args:
            current_state: 当前即将进入的状态
            context: 包含 artifacts 字典的执行上下文

        Raises:
            ProcessViolationError: 流程违规
        """
        import time
        from orbit.observability.trace import SpanStatus, TraceCollector

        _t0 = time.monotonic()
        span = TraceCollector.start_span(
            self.task_id, component="guard", action="check",
            input_summary=f"state={current_state.value}",
        )
        self._visited.add(current_state)

        # 检查1: 强制状态是否已被访问或将被访问
        for mandatory in self.MANDATORY_STATES:
            if mandatory not in self._visited:
                # 检查是否已经被越过
                if _STATE_ORDER.get(current_state, 0) > _STATE_ORDER.get(mandatory, 0):
                    raise ProcessViolationError(
                        self.task_id,
                        "earlier_state",
                        current_state.value,
                        f"强制状态 {mandatory.value} 未执行——LLM 不得跳过",
                    )

        # 检查2: PLANNING 跳过权限
        if (
            current_state == TaskState.CODING
            and TaskState.PLANNING not in self._visited
            and not self._fast_lane
        ):
            raise ProcessViolationError(
                self.task_id,
                TaskState.PARSING.value,
                TaskState.CODING.value,
                "跳过 PLANNING 需要 ComplexityScorer 授权快车道——LLM 不得自行决定",
            )

        # 检查3: VERIFYING 跳过权限
        if (
            current_state == TaskState.DONE
            and TaskState.VERIFYING not in self._visited
            and not self._fast_lane
        ):
            raise ProcessViolationError(
                self.task_id,
                TaskState.CODING.value,
                TaskState.DONE.value,
                "跳过 VERIFYING 需要 ComplexityScorer 授权快车道——LLM 不得自行决定",
            )

        # 检查4: 上一状态是否有产物
        prev_state = self._get_previous_state(current_state)
        if prev_state and prev_state not in (TaskState.IDLE,):
            artifacts = context.get("artifacts", {})
            if artifacts.get(prev_state.value) is None:
                raise ProcessViolationError(
                    self.task_id,
                    prev_state.value,
                    current_state.value,
                    f"状态 {prev_state.value} 无产物——流程不完整",
                )

        TraceCollector.end_span(
            span, status=SpanStatus.OK,
            output_summary=f"guard_passed_{current_state.value}",
            duration_ms=(time.monotonic() - _t0) * 1000,
        )
        logger.debug(
            "process_guard_check_passed",
            task_id=self.task_id,
            state=current_state.value,
            visited=[s.value for s in self._visited],
        )

    # ── 内部 ──────────────────────────────────────────

    def _get_previous_state(self, current: TaskState) -> TaskState | None:
        """获取当前状态的前驱状态。"""
        transitions = FAST_LANE_TRANSITIONS if self._fast_lane else FULL_PIPELINE_TRANSITIONS
        for prev, nxt in transitions.items():
            if nxt == current:
                return prev
        return None

    @property
    def fast_lane(self) -> bool:
        return self._fast_lane

    @property
    def visited_states(self) -> frozenset[TaskState]:
        return frozenset(self._visited)
