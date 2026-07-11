"""调度器骨架——Orbit 编排层入口（内部减熵 P1）.

P1 重构: 697 行 Scheduler 拆为三层——
  Scheduler(本文件)    入口 + 状态转换 + 黄金路由
  TaskRunner(task_runner.py)  单任务生命周期
  DagRunner(dag_runner.py)    DAG 编排
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.agents.factory import AgentFactory
    from orbit.communication.message_bus import AgentMessageBus
    from orbit.compression.budget import TokenBudgetTracker
    from orbit.compression.compressor import ContextCompressor
    from orbit.gateway.client import LLMClient
    from orbit.goal.intake_router import IntakeRouter
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.observability.audit import AuditLogger
    from orbit.tools.registry import ToolRegistry

import structlog

from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointManager
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload
from orbit.gateway.client import LLMClient
from orbit.scheduler.dag_runner import DagRunner
from orbit.scheduler.graph import NodeStatus, TaskGraph
from orbit.scheduler.task_runner import TaskRunner

logger = structlog.get_logger("orbit.scheduler.orchestrator")


class SchedulerError(Exception):
    pass


class Scheduler:
    """Orbit 编排层入口——委托 TaskRunner + DagRunner 执行."""

    _compose_orchestrator: object | None = None  # Phase 2: ComposeOrchestrator——main.py 注入

    GOLDEN_ROUTE: dict[str, list[str]] = {
        "实现新功能": ["architect", "developer"],
        "修复Bug": ["qa", "developer", "reviewer"],
        "代码审查": ["reviewer"],
        "重构": ["architect", "developer"],
        "数据分析": ["developer"],
    }

    def __init__(
        self,
        agent_llms: dict[str, LLMClient] | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        event_bus: EventBus | None = None,
        max_concurrent: int = 3,
        node_timeout: int = 30,
        max_retries: int = 2,
        fail_fast: bool = True,
        agent_factory: type[AgentFactory] | None = None,
        compressor: ContextCompressor | None = None,
        budget_tracker: TokenBudgetTracker | None = None,
        message_bus: AgentMessageBus | None = None,
        tool_registry: ToolRegistry | None = None,
        router: IntakeRouter | None = None,
        audit_logger: AuditLogger | None = None,
        graph: CodeGraphEngine | None = None,  # G2: 图谱引擎——Stage 2 符号查询
    ):
        self._agent_llms = agent_llms or {}
        self.checkpoint = checkpoint_manager
        self._event_bus = event_bus
        self._agent_factory = agent_factory
        self._compressor = compressor
        self._budget_tracker = budget_tracker
        self._message_bus = message_bus  # P1-5: 保存 message_bus
        self._tool_registry = tool_registry
        self._audit_logger = audit_logger
        self.router = router
        self._fast_lane = False
        # PR3: 运行中任务注册表——task_id → asyncio.Task，供 cancel_task 按 id 取消
        self._active_tasks: dict[str, asyncio.Task] = {}

        self._task_runner = TaskRunner(
            agent_factory=agent_factory,
            agent_llms=self._agent_llms,
            checkpoint=checkpoint_manager,
            event_bus=event_bus,
            compressor=compressor,
            budget_tracker=budget_tracker,  # P1-4: 传递 budget_tracker
            tool_registry=tool_registry,
            audit_logger=audit_logger,
            router=router,
            graph=graph,  # G2: 图谱引擎——Stage 2 L2 填充
        )
        self._dag_runner = DagRunner(
            checkpoint=checkpoint_manager,
            event_bus=event_bus,
            max_concurrent=max_concurrent,
            node_timeout=node_timeout,
            max_retries=max_retries,
            fail_fast=fail_fast,
        )

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        return await self._task_runner.run_task(task_id, prd)

    def spawn_task(self, task_id: str, prd: str) -> asyncio.Task:
        """后台启动任务并登记到注册表，返回 asyncio.Task 供追踪/取消。

        PR3: 替代裸 asyncio.create_task(run_task)——让运行中任务可按 task_id 取消。
        P1-1 修复：同 task_id 已有运行中任务则直接返回它，避免重复 spawn 污染注册表；
        done_callback 做身份校验，只清理自己那一条（防误删后来的同 id 任务）。
        """
        existing = self._active_tasks.get(task_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(self.run_task(task_id, prd))
        self._active_tasks[task_id] = task
        task.add_done_callback(
            lambda t: self._active_tasks.pop(task_id, None) if self._active_tasks.get(task_id) is t else None
        )
        return task

    async def cancel_task(self, task_id: str) -> bool:
        """按 task_id 取消运行中任务并写 CANCELLED 检查点。

        PR3: 若任务在注册表则 .cancel()（触发 CancelledError 停止协程）；
        无论是否在跑，都写 CANCELLED 检查点（乐观锁 version+1 防被旧写覆盖）。
        返回是否成功写入取消状态。
        """
        running = self._active_tasks.pop(task_id, None)
        if running is not None and not running.done():
            running.cancel()
        if self.checkpoint is None:
            return False
        # WHY 读旧检查点拿 version：乐观锁递增，避免被正在收尾的协程旧状态覆盖
        prev = await self.checkpoint.load(task_id)
        from orbit.checkpoint.manager import CheckpointData

        data = CheckpointData(
            task_id=task_id,
            state=TaskState.CANCELLED.value,
            progress=prev.progress if prev else 0.0,
            context=prev.context if prev else {},
            version=(prev.version + 1) if prev else 1,
        )
        await self.checkpoint.save(task_id, data)
        return True

    async def resume(self, task_id: str) -> TaskState | None:
        return await self._task_runner.resume(task_id)

    async def run_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        return await self._dag_runner.run_dag(graph)

    async def resume_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        return await self._dag_runner.resume_dag(graph)

    def _route_by_golden_why(self, context: dict[str, Any]) -> list[str]:
        why = str(context.get("golden_why", ""))
        route = self.GOLDEN_ROUTE.get(why)
        if route:
            logger.info("golden_route_match", why=why, route=route)
            return route
        return ["developer"]

    def _publish_task_update(
        self,
        task_id: str,
        state: str,
        progress: float,
        dag: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        output = None
        if state in ("CODING", "DONE") and context:
            output = context.get("artifacts", {}).get("CODING")
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
        self,
        task_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
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


def generate_task_id() -> str:
    return uuid.uuid4().hex
