"""TaskRunner——单任务生命周期执行器（内部减熵 P1）.

从 Scheduler 拆出: run_task / _agent_cycle / _run_agent / _build_context /
save_checkpoint / resume / _continue_from.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orbit.agents.factory import AgentFactory
    from orbit.compression.compressor import ContextCompressor
    from orbit.tools.registry import ToolRegistry

import structlog

from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload

logger = structlog.get_logger()

# 状态→角色映射（从 Scheduler._agent_cycle 移出）
ROLE_MAP: dict[TaskState, str] = {
    TaskState.IDLE: "clarifier",
    TaskState.PARSING: "clarifier",
    TaskState.PLANNING: "architect",
    TaskState.CODING: "developer",
    TaskState.VERIFYING: "reviewer",
}

TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}


class TaskRunner:
    """单任务生命周期——状态机驱动 Agent 循环.

    用法:
        runner = TaskRunner(
            scheduler=scheduler,  # 共享组件通过 Scheduler 传入
        )
        final_state = await runner.run_task(task_id, prd)
    """

    def __init__(
        self,
        *,
        agent_factory: type[AgentFactory] | None = None,
        agent_llms: dict[str, Any] | None = None,
        checkpoint: CheckpointManager | None = None,
        event_bus: EventBus | None = None,
        compressor: ContextCompressor | None = None,
        budget_tracker: Any = None,  # P1-4: budget_tracker 注入
        tool_registry: ToolRegistry | None = None,
        audit_logger: Any = None,
        router: Any = None,
        fast_lane: bool = False,
    ) -> None:
        self._agent_factory = agent_factory
        self._agent_llms = agent_llms or {}
        self.checkpoint = checkpoint
        self._event_bus = event_bus
        self._compressor = compressor
        self._budget_tracker = budget_tracker  # P1-4
        self._tool_registry = tool_registry
        self._audit_logger = audit_logger
        self.router = router
        self._fast_lane = fast_lane

    # ── 公共入口 ────────────────────────────────────────

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        """运行单个任务：IDLE → ... → DONE/FAILED."""
        state = TaskState.IDLE
        await self._save_checkpoint(task_id, state, {"prd": prd})
        context: dict[str, Any] = {"prd": prd, "artifacts": {}, "mode": "auto"}

        # 复杂度评估→决定快车道
        if context.get("mode") == "auto":
            from orbit.scheduler.complexity import ComplexityScorer

            scorer = ComplexityScorer()
            c_result = scorer.evaluate(prd)
            self._fast_lane = c_result.recommended_mode == "fast"
            context["complexity"] = c_result.to_dict()

        while state not in TERMINAL_STATES:
            try:
                observation = await self._agent_cycle(task_id, state, context)
                context["artifacts"][state.value] = observation
                self._publish_task_update(
                    task_id, state.value, _state_to_progress(state), context=context
                )
                state = _transition(state, self._fast_lane)
                await self._save_checkpoint(task_id, state, context)
            except asyncio.CancelledError:
                raise  # P0-1: 不吞取消信号，保持协作式取消语义
            except Exception as e:
                logger.error("task_failed", task_id=task_id, state=state.value, error=str(e))
                state = TaskState.FAILED
                await self._save_checkpoint(task_id, state, {**context, "error": str(e)})
                return state

        return state

    async def resume(self, task_id: str) -> TaskState | None:
        """从检查点恢复任务."""
        if self.checkpoint is None:
            return None
        data = await self.checkpoint.load(task_id)
        if data is None:
            return None
        state = TaskState(data.state)
        if state in TERMINAL_STATES:
            return state
        context = data.context
        return await self._continue_from(task_id, state, context)

    # ── Agent 循环 ──────────────────────────────────────

    async def _agent_cycle(self, task_id: str, state: TaskState, context: dict[str, Any]) -> str:
        """单个 Agent 循环——按状态映射角色→拉起 Agent 执行."""
        role = ROLE_MAP.get(state)
        if role and self._agent_factory is not None:
            context["state"] = state.value
            context["agent_name"] = role

            if state == TaskState.PLANNING and self.router is not None:
                try:
                    complexity = context.get("complexity", {})
                    decision = await self.router.evaluate(
                        file_count=complexity.get("file_count", 1),
                        change_type=complexity.get("scope", "single_file"),
                        risk=complexity.get("risk", "low"),
                        agent_role=role,
                        has_similar_history=False,
                    )
                    context["model_tier"] = decision.tier.value
                    context["router_decision"] = decision
                except asyncio.CancelledError:
                    raise  # P2-10: 不吞取消信号
                except Exception as e:
                    logger.warning("router_evaluate_failed", error=str(e))

            return await self._run_agent(role, task_id, context)

        raise RuntimeError(f"状态 {state.value} 无 Agent 角色映射，Orbit 不支持直接 LLM 调用。")

    async def _run_agent(
        self, role: str, task_id: str, context: dict[str, Any], timeout: int = 300
    ) -> str:
        """拉起 Agent 协程——AgentFactory 创建 + 注入依赖 + 超时保护."""
        if self._agent_factory is None:
            raise RuntimeError("AgentFactory 未配置")

        agent_llm = self._agent_llms.get(role) if self._agent_llms else None

        try:
            agent = self._agent_factory.create(
                role,
                llm=agent_llm,
                compressor=self._compressor,
                budget_tracker=self._budget_tracker,  # P1-4: 传递 budget_tracker
            )
        except Exception as e:
            logger.error("agent_build_failed", role=role, error=str(e))
            if self._audit_logger:
                self._audit_logger.log(
                    "orchestrator",
                    "agent_build_failed",
                    task_id=task_id,
                    status="error",
                    error=str(e),
                )
            return f"[error] Agent {role} 创建失败: {e}"

        agent_context = self._build_context(task_id, context)

        if self._audit_logger:
            self._audit_logger.log("orchestrator", "agent_start", task_id=task_id, role=role)

        try:
            from orbit.agents.base import AgentInput

            ctx_dict = agent_context.to_dict() if hasattr(agent_context, "to_dict") else {}
            agent_input = AgentInput(
                task=ctx_dict.get("l3", {}).get("prd", ""),
                context=ctx_dict,
                role=role,  # type: ignore[arg-type]
            )
            output_obj = await asyncio.wait_for(agent.execute(agent_input), timeout=timeout)
            if output_obj.status == "ok":
                r = output_obj.result
                output = r.get("design") or r.get("code") or r.get("review") or str(r)
            else:
                raise RuntimeError(f"Agent {role} 返回错误: {output_obj.error}")
        except TimeoutError:  # P1-6: 兼容 Python <3.11
            logger.warning("agent_timeout", role=role, task_id=task_id)
            raise
        except asyncio.CancelledError:
            raise  # P0-1: 不吞取消信号
        except Exception as e:
            logger.error("agent_run_error", role=role, task_id=task_id, error=str(e))
            if self._audit_logger:
                self._audit_logger.log(
                    "orchestrator", "agent_run_error", task_id=task_id, role=role, error=str(e)
                )
            raise

        return str(output)

    def _build_context(self, task_id: str, context: dict[str, Any]) -> Any:
        """构建 L1-L5 TaskContext."""
        from orbit.agents.context import TaskContext

        l4: dict[str, Any] = {}
        try:
            from orbit.memory.models import MemoryFileType
            from orbit.memory.store import MemoryStore

            project_path = context.get("project_path", "")
            store = MemoryStore(project_path=project_path)
            mem = store.read_file(MemoryFileType.EPISODIC)
            if mem.body:
                l4["working_memory"] = mem.body[:2000]
            progress = store.read_file(MemoryFileType.PROGRESS)
            if progress.body:
                l4["progress"] = progress.body[:1000]
        except asyncio.CancelledError:
            raise  # P2-11: 不吞取消信号
        except Exception:
            logger.debug("memory_load_skipped", task_id=task_id)  # P2-11: 至少记日志

        return TaskContext(
            task_id=task_id,
            agent_name=context.get("agent_name", ""),
            model_tier=context.get("model_tier", ""),
            l1="遵循小企业会计准则; 禁止直接操作总账; 金额使用 Decimal",
            l2=context.get("l2", {}),
            l3={
                "state": context.get("state", "UNKNOWN"),
                "prd": context.get("prd", ""),
                "artifacts": context.get("artifacts", {}),
            },
            l4=l4,
            l5=context.get("l5", []),
        )

    async def _continue_from(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> TaskState:
        """从指定状态继续执行."""
        current = state
        while current not in TERMINAL_STATES:
            try:
                observation = await self._agent_cycle(task_id, current, context)
                context.setdefault("artifacts", {})[current.value] = observation
                current = _transition(current, self._fast_lane)
                await self._save_checkpoint(task_id, current, context)
            except asyncio.CancelledError:
                raise  # P0-1: 不吞取消信号
            except Exception as e:
                logger.error("resume_failed", task_id=task_id, error=str(e))
                current = TaskState.FAILED
                await self._save_checkpoint(task_id, current, {**context, "error": str(e)})
                return current
        return current

    # ── 检查点 + 事件 ──────────────────────────────────

    async def _save_checkpoint(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> None:
        """保存检查点."""
        if self.checkpoint is None:
            return
        data = CheckpointData(  # type: ignore[call-arg]
            task_id=task_id,
            state=state.value,
            progress=_state_to_progress(state),
            context=context,
        )
        await self.checkpoint.save(task_id, data)

    def _publish_task_update(
        self,
        task_id: str,
        state: str,
        progress: float,
        dag: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """发布 task:update 事件."""
        if self._event_bus is None:
            return
        output: str | None = None
        if state in ("CODING", "DONE") and context:
            artifacts = context.get("artifacts", {})
            output = artifacts.get("CODING")
        self._event_bus.publish(
            DashboardEvent(
                type="task:update",
                task_id=task_id,
                payload=TaskUpdatePayload(
                    task_id=task_id,
                    state=state,
                    progress=progress,
                    dag=dag or [],
                    timestamp=datetime.now(UTC).isoformat(),
                    output=output,
                ).model_dump(),
            )
        )

    def _publish_token_update(
        self, task_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int
    ) -> None:
        """发布 token:update 事件."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DashboardEvent(
                type="token:update",
                task_id=task_id,
                payload=TokenUpdatePayload(
                    task_id=task_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    timestamp=datetime.now(UTC).isoformat(),
                ).model_dump(),
            )
        )


# ── 共享工具函数 ────────────────────────────────────────

STATE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

FAST_LANE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,
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
        TaskState.PLANNING: 0.4,
        TaskState.CODING: 0.7,
        TaskState.VERIFYING: 0.9,
        TaskState.DONE: 1.0,
        TaskState.FAILED: 1.0,
        TaskState.CANCELLED: 1.0,
    }
    return mapping.get(state, 0.0)
