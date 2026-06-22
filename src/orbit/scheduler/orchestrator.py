"""MVP-01 调度器骨架（状态机 + Agent 循环原型）。

WHY 这是骨架而非完整实现：MVP 阶段只跑通单任务串行闭环（IDLE→PLANNING→CODING→VERIFYING→DONE），
Step 5.1 会扩展为 DAG 并发执行 + 拓扑排序。

Agent 循环：思考（LLM 生成计划/代码）→ 行动（执行）→ 观察（收集结果）→ 状态转换。
每次状态转换后保存检查点（崩溃可恢复）。
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.gateway.client import LLMClient
from orbit.gateway.schemas import LLMRequest

logger = structlog.get_logger()

# MVP 调度器状态转换图（串行单路径）
# Step 5.1 会扩展为 DAG（PENDING/RUNNING/SUCCESS/FAILED/SKIPPED + 拓扑排序）
STATE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

# 终态（不可转换）
TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}


class SchedulerError(Exception):
    """调度器错误基类。"""


class InvalidStateTransitionError(SchedulerError):
    """非法状态转换（如 DONE → CODING）。"""


class Scheduler:
    """MVP 调度器骨架：单任务串行状态机 + Agent 循环原型。

    被调度器 API 调用（Step 1.1 的 /tasks POST 创建后触发）。
    依赖 LLMClient（思考）+ CheckpointManager（状态持久化）。
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ):
        self.llm = llm_client
        self.checkpoint = checkpoint_manager

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        """运行单个任务：IDLE → ... → DONE/FAILED。

        Agent 循环原型：每个状态对应一个 Think-Act-Observe 周期。
        WHY MVP 串行：单任务单路径，Step 5.1 扩展 DAG 并发。
        """
        state = TaskState.IDLE
        await self._save_checkpoint(task_id, state, {"prd": prd})
        context: dict[str, Any] = {"prd": prd, "artifacts": {}}

        while state not in TERMINAL_STATES:
            try:
                # Think-Act-Observe 循环
                observation = await self._agent_cycle(task_id, state, context)
                context["artifacts"][state.value] = observation
                # 状态转换
                next_state = self._transition(state)
                state = next_state
                await self._save_checkpoint(task_id, state, context)
                logger.info(
                    "state_transition",
                    task_id=task_id,
                    to=state.value,
                )
            except Exception as e:
                # MVP 策略：任何异常 → FAILED（Step 5.x 加重试）
                logger.error(
                    "task_failed",
                    task_id=task_id,
                    state=state.value,
                    error=str(e),
                )
                state = TaskState.FAILED
                await self._save_checkpoint(task_id, state, {**context, "error": str(e)})
                return state

        return state

    def _transition(self, current: TaskState) -> TaskState:
        """执行状态转换。非法转换抛 InvalidStateTransitionError。"""
        if current in TERMINAL_STATES:
            raise InvalidStateTransitionError(f"终态 {current.value} 不可转换")
        if current not in STATE_TRANSITIONS:
            raise InvalidStateTransitionError(f"状态 {current.value} 无定义的后继状态")
        return STATE_TRANSITIONS[current]

    async def _agent_cycle(self, task_id: str, state: TaskState, context: dict[str, Any]) -> str:
        """单个 Agent 循环：思考（LLM）→ 行动 → 观察。

        MVP 阶段每个状态都调一次 LLM，返回内容作为观察结果。
        Step 5.2 会按状态分配不同 Agent 角色（架构/开发/审查）。
        """
        if self.llm is None:
            # MVP 无 LLM 时返回占位（测试用）
            return f"[mock] {state.value} 完成"
        # 根据状态构造不同的 prompt（Step 5.2 细化为 Agent 角色模板）
        prompt = self._build_prompt(state, context)
        resp = await self.llm.generate(
            LLMRequest(prompt=prompt, system_prompt=self._system_prompt(state)),  # type: ignore[call-arg]
            task_id=task_id,
        )
        return resp.content

    def _build_prompt(self, state: TaskState, context: dict[str, Any]) -> str:
        """按状态构造 prompt。"""
        prd = context.get("prd", "")
        if state == TaskState.IDLE:
            return f"分析以下需求，输出关键信息：\n{prd}"
        if state == TaskState.PARSING:
            return f"解析需求，列出功能点：\n{prd}"
        if state == TaskState.PLANNING:
            prev = context.get("artifacts", {}).get("PARSING", "")
            return f"基于解析结果设计实现方案：\n{prev}"
        if state == TaskState.CODING:
            plan = context.get("artifacts", {}).get("PLANNING", "")
            return f"基于方案生成代码：\n{plan}"
        if state == TaskState.VERIFYING:
            code = context.get("artifacts", {}).get("CODING", "")
            return f"验证以下代码的正确性：\n{code}"
        return prd  # type: ignore[no-any-return]

    def _system_prompt(self, state: TaskState) -> str:
        """编排层风格的 System Prompt（Step 0.4 架构锚定）。"""
        return (
            f"你是 V14.1 多智能体协作网络中的 {state.value} 阶段执行 Agent。"
            "在协作契约约束下工作，输出必须通过 L1-L8 验证。"
        )

    async def _save_checkpoint(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> None:
        """保存检查点（每次状态转换后）。"""
        if self.checkpoint is None:
            return
        data = CheckpointData(  # type: ignore[call-arg]
            task_id=task_id,
            state=state.value,
            progress=self._state_to_progress(state),
            context=context,
        )
        await self.checkpoint.save(task_id, data)

    @staticmethod
    def _state_to_progress(state: TaskState) -> float:
        """状态映射到进度（0.0-1.0）。"""
        mapping = {
            TaskState.IDLE: 0.0,
            TaskState.PARSING: 0.2,
            TaskState.PLANNING: 0.4,
            TaskState.CODING: 0.7,
            TaskState.VERIFYING: 0.9,
            TaskState.DONE: 1.0,
            TaskState.FAILED: 1.0,
            TaskState.CANCELLED: 1.0,
        }
        return mapping.get(state, 0.0)

    async def resume(self, task_id: str) -> TaskState | None:
        """从检查点恢复任务（崩溃后重启）。

        加载检查点，从断点状态继续执行。
        """
        if self.checkpoint is None:
            return None
        data = await self.checkpoint.load(task_id)
        if data is None:
            return None
        state = TaskState(data.state)
        if state in TERMINAL_STATES:
            return state
        # 从断点继续（简化：重新跑剩余状态）
        context = data.context
        logger.info(
            "task_resumed",
            task_id=task_id,
            from_state=state.value,
        )
        return await self._continue_from(task_id, state, context)

    async def _continue_from(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> TaskState:
        """从指定状态继续执行。

        WHY 时序说明（PR#3 P2-2）：run_task 首次保存初始 IDLE 状态，
        而 _continue_from 从断点状态继续，首次保存的是断点转换后的下一状态。
        断点状态本身的 artifact 已在 context 中（崩溃前已保存），
        所以无需重复保存断点状态。语义与 run_task 不对称但功能正确。
        """
        current = state
        while current not in TERMINAL_STATES:
            try:
                observation = await self._agent_cycle(task_id, current, context)
                context.setdefault("artifacts", {})[current.value] = observation
                current = self._transition(current)
                await self._save_checkpoint(task_id, current, context)
            except Exception as e:
                logger.error("resume_failed", task_id=task_id, error=str(e))
                current = TaskState.FAILED
                await self._save_checkpoint(task_id, current, {**context, "error": str(e)})
                return current
        return current


def generate_task_id() -> str:
    """生成任务 ID（uuid4 hex，与 API 层一致）。

    WHY 保留为公共 API：调度器外部入口（API 层创建任务/CLI 工具）可能复用，
    当前 API 层独立生成 ID，此方法供测试和未来 CLI 用。
    """
    return uuid.uuid4().hex
