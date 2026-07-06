"""调度器骨架——Orbit 编排层入口（内部减熵 P1）.

P1 重构: 697 行 Scheduler 拆为三层——
  Scheduler(本文件)    入口 + 状态转换 + 黄金路由
  TaskRunner(task_runner.py)  单任务生命周期
  DagRunner(dag_runner.py)    DAG 编排
"""

from __future__ import annotations

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
