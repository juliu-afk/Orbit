"""MVP-01 调度器骨架（状态机 + Agent 循环原型）+ Step 5.1 DAG 扩展。

WHY 这是骨架而非完整实现：MVP 阶段只跑通单任务串行闭环（IDLE→PLANNING→CODING→VERIFYING→DONE），
Step 5.1 扩展为 DAG 并发执行 + 拓扑排序。

Agent 循环：思考（LLM 生成计划/代码）→ 行动（执行）→ 观察（收集结果）→ 状态转换。
每次状态转换后保存检查点（崩溃可恢复）。

Step 6.1：注入 EventBus，状态/Token/告警变更时发布事件供 Dashboard 消费。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orbit.agents.factory import AgentFactory
    from orbit.observability.audit import AuditLogger
    from orbit.tools.registry import ToolRegistry

import structlog

from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload
from orbit.gateway.client import LLMClient
from orbit.scheduler.graph import GraphNode, NodeStatus, TaskGraph

logger = structlog.get_logger()

# MVP 调度器状态转换图（串行单路径）
STATE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

# Step O1 快车道路径（跳过 PLANNING，轻量验证）
FAST_LANE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,  # 跳过 PLANNING
    TaskState.CODING: TaskState.DONE,  # 跳过 VERIFYING
    TaskState.DONE: TaskState.DONE,
}

# 终态（不可转换）
TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}


class SchedulerError(Exception):
    """调度器错误基类。"""


class InvalidStateTransitionError(SchedulerError):
    """非法状态转换（如 DONE → CODING）。"""


class Scheduler:
    """MVP 调度器骨架：单任务串行状态机 + Agent 循环原型。

    Orbit 定位编排层——只调度 Agent，不直接调用 LLM。
    每个 Agent 角色通过注入的 LLMClient 实例调用其配置的模型。
    """

    def __init__(
        self,
        agent_llms: dict[str, LLMClient] | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        event_bus: EventBus | None = None,
        max_concurrent: int = 3,
        node_timeout: int = 30,
        max_retries: int = 2,
        fail_fast: bool = True,
        # ── Step I1 集成胶水 ──────────────────────
        agent_factory: type[AgentFactory] | None = None,  # AgentFactory (延迟导入避免循环)
        compressor: object | None = None,  # Phase 2 AC7: ContextCompressor
        budget_tracker: object | None = None,  # Phase 2 AC7: TokenBudgetTracker
        message_bus: Any = None,  # AgentMessageBus (通信层未导出类型)
        tool_registry: ToolRegistry | None = None,  # ToolRegistry
        # ── Step 2.3 智能路由 ─────────────────────
        router: Any = None,  # RouterAgent（延迟导入，内部模块无公开类型）
        audit_logger: AuditLogger | None = None,  # AuditLogger
    ):
        self._agent_llms = agent_llms or {}
        self.checkpoint = checkpoint_manager
        self._event_bus = event_bus
        # Step 5.1 DAG 配置
        self._max_concurrent = max_concurrent
        self._node_timeout = node_timeout
        self._max_retries = max_retries
        self._fail_fast = fail_fast
        # Step I1 集成
        self._agent_factory = agent_factory
        self._message_bus = message_bus
        self._tool_registry = tool_registry
        self._audit_logger = audit_logger
        self._compressor = compressor  # Phase 2 AC7
        self._budget_tracker = budget_tracker  # Phase 2 AC7
        self.router = router  # Step 2.3: RouterAgent（可选）
        # Step O1: 快车道模式
        self._fast_lane = False

    def _publish_task_update(
        self,
        task_id: str,
        state: str,
        progress: float,
        dag: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """发布 task:update 事件到 EventBus（非阻塞）。

        WHY 抽方法而非内联：多个代码路径（run_task/run_dag/resume）
        都需推送状态更新，统一入口避免遗漏。
        event_bus 为 None 时静默跳过——不影响无 Dashboard 场景。
        """
        if self._event_bus is None:
            return
        # 提取代码产物——CODING/DONE 状态时推送生成的代码到前端
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
        """发布 token:update 事件（非阻塞）。

        每次 LLM 调用完成后推送，供 Dashboard Token 折线图消费。
        """
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

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        """运行单个任务：IDLE → ... → DONE/FAILED。

        Agent 循环原型：每个状态对应一个 Think-Act-Observe 周期。
        WHY MVP 串行：单任务单路径，Step 5.1 扩展 DAG 并发。
        """
        state = TaskState.IDLE
        await self._save_checkpoint(task_id, state, {"prd": prd})
        context: dict[str, Any] = {"prd": prd, "artifacts": {}, "mode": "auto"}

        # Step O1: 任务复杂度评估 → 决定快车道还是完整流水线
        if context.get("mode") == "auto":
            from orbit.scheduler.complexity import ComplexityScorer

            scorer = ComplexityScorer()
            c_result = scorer.evaluate(prd)
            self._fast_lane = c_result.recommended_mode == "fast"
            context["complexity"] = c_result.to_dict()
            logger.info(
                "complexity_evaluated",
                task_id=task_id,
                score=c_result.score,
                mode=c_result.recommended_mode,
            )

        while state not in TERMINAL_STATES:
            try:
                # Think-Act-Observe 循环
                observation = await self._agent_cycle(task_id, state, context)
                context["artifacts"][state.value] = observation
                # Step 6.1：推送状态变更到 Dashboard（含代码产物）
                # WHY 先推后转：转换后 state 已变（如 CODING→VERIFYING），
                # 此时推送 state.value 才是当前阶段的正确状态，output 才能匹配
                self._publish_task_update(
                    task_id, state.value, self._state_to_progress(state), context=context
                )
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

    # Phase 2: 黄金圈 Why 路由表
    GOLDEN_ROUTE: dict[str, list[str]] = {
        "实现新功能": ["architect", "developer"],
        "修复Bug": ["qa", "developer", "reviewer"],
        "代码审查": ["reviewer"],
        "重构": ["architect", "developer"],
        "数据分析": ["developer"],
    }

    def _route_by_golden_why(self, context: dict[str, Any]) -> list[str]:
        """按黄金圈 Why 分类选择初始 Agent 链。

        WHY 独立方法: 路由逻辑与调度逻辑分离，方便测试和扩展。
        默认回退 developer——向后兼容无标签的旧调用。
        """
        why = str(context.get("golden_why", ""))
        route = self.GOLDEN_ROUTE.get(why)
        if route:
            logger.info("golden_route_match", why=why, route=route)
            return route
        # 默认回退——向后兼容
        logger.debug("golden_route_default", why=why or "empty")
        return ["developer"]

    def _transition(self, current: TaskState) -> TaskState:
        """执行状态转换。快车道模式走简化路径。"""
        if current in TERMINAL_STATES:
            raise InvalidStateTransitionError(f"终态 {current.value} 不可转换")
        transitions = FAST_LANE_TRANSITIONS if self._fast_lane else STATE_TRANSITIONS
        if current not in transitions:
            raise InvalidStateTransitionError(f"状态 {current.value} 无定义的后继状态")
        return transitions[current]

    # ── Step I1 集成胶水 ──────────────────────────────

    async def _run_agent(
        self, role: str, task_id: str, context: dict[str, Any], timeout: int = 300
    ) -> str:
        """拉起 Agent 协程——AgentFactory 创建 + 注入依赖 + 超时保护。

        role: architect | developer | reviewer | tester | devops
        超时 5 分钟后取消协程。
        """
        if self._agent_factory is None:
            raise RuntimeError(
                "AgentFactory 未配置。Orbit 编排层必须通过 Agent 执行任务，"
                "不支持直接 LLM 调用。请在 Scheduler 初始化时注入 AgentFactory。"
            )

        agent_llm = self._agent_llms.get(role) if self._agent_llms else None

        try:
            agent = self._agent_factory.create(
                role, llm=agent_llm,
                compressor=self._compressor,
                budget_tracker=self._budget_tracker,
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

        # 构建 L1-L5 上下文
        agent_context = self._build_context(task_id, context)

        # 记录审计
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
        except TimeoutError:
            logger.warning("agent_timeout", role=role, task_id=task_id)
            if self._audit_logger:
                self._audit_logger.log("orchestrator", "agent_timeout", task_id=task_id, role=role)
            raise
        except Exception as e:
            logger.error("agent_run_error", role=role, task_id=task_id, error=str(e))
            if self._audit_logger:
                self._audit_logger.log(
                    "orchestrator", "agent_run_error", task_id=task_id, role=role, error=str(e)
                )
            raise

        return str(output)

    def _build_context(self, task_id: str, context: dict[str, Any]) -> Any:
        """构建 L1-L5 TaskContext——注入给 Agent.run()。

        L1: 协作宪法 (章程规则)
        L2: 四图谱查询结果 (占位)
        L3: 任务状态
        L4: Agent 私有工作记忆
        L5: 长期记忆 (教训库)
        """
        from orbit.agents.context import TaskContext

        # Phase 2: L4——从文件记忆系统加载 Agent 工作记忆
        l4: dict[str, Any] = {}
        try:
            from orbit.memory.models import MemoryFileType
            from orbit.memory.store import MemoryStore

            project_path = context.get("project_path", "")
            store = MemoryStore(project_path=project_path)
            mem = store.read_file(MemoryFileType.EPISODIC)
            if mem.body:
                l4["working_memory"] = mem.body[:2000]
            # 也检查 progress
            progress = store.read_file(MemoryFileType.PROGRESS)
            if progress.body:
                l4["progress"] = progress.body[:1000]
        except Exception:
            pass  # 记忆加载失败不阻塞任务

        return TaskContext(
            task_id=task_id,
            agent_name=context.get("agent_name", ""),  # Step 2.3
            model_tier=context.get("model_tier", ""),  # Step 2.3
            l1="遵循小企业会计准则; 禁止直接操作总账; 金额使用 Decimal",
            l2=context.get("l2", {}),  # 图谱查询结果由调用方注入
            l3={
                "state": context.get("state", "UNKNOWN"),
                "prd": context.get("prd", ""),
                "artifacts": context.get("artifacts", {}),
            },
            l4=l4,  # Phase 2: 私有工作记忆——从 MEMORY.md 加载
            l5=context.get("l5", []),  # 教训库检索结果
        )

    async def _agent_cycle(self, task_id: str, state: TaskState, context: dict[str, Any]) -> str:
        """单个 Agent 循环：按状态映射角色 → 拉起 Agent 执行。

        Orbit 只编排 Agent，不直接调 LLM。无 AgentFactory 时抛错。
        """
        # 状态→角色映射
        role_map: dict[TaskState, str] = {
            TaskState.IDLE: "clarifier",
            TaskState.PARSING: "clarifier",
            TaskState.PLANNING: "architect",
            TaskState.CODING: "developer",
            TaskState.VERIFYING: "reviewer",
        }
        role = role_map.get(state)
        if role and self._agent_factory is not None:
            context["state"] = state.value
            context["agent_name"] = role  # Step 2.3: 记录当前 Agent 名称

            # Step 2.3: PLANNING 阶段调用 RouterAgent 评估模型级别
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
                    logger.info(
                        "router_tier_selected",
                        task_id=task_id,
                        role=role,
                        tier=decision.tier.value,
                        confidence=round(decision.confidence, 2),
                    )
                except Exception as e:
                    logger.warning("router_evaluate_failed", error=str(e))

            return await self._run_agent(role, task_id, context)

        raise RuntimeError(
            f"状态 {state.value} 无 Agent 角色映射，且 Orbit 不支持直接 LLM 调用。"
            "请配置 AgentFactory 和 agent_llms。"
        )

    async def _save_checkpoint(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> None:
        """保存检查点（每次状态转换后）。"""
        if self.checkpoint is None:
            return
        # Pydantic 2.x + mypy strict 已知兼容问题：所有字段有 default 但
        # mypy 仍要求显式传参。不是真实类型错误。
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

    def _publish_dag_update(self, graph: TaskGraph) -> None:
        """发布 DAG 状态快照到 Dashboard（非阻塞）。

        WHY 独立于 _publish_task_update：DAG 节点级更新频率高
        （每节点状态变更一次），字段不同，单独处理。
        """
        if self._event_bus is None:
            return
        dag_nodes = [
            {
                "id": n.id,
                "agent_role": n.agent_role,
                "status": n.status.value,
                "duration_ms": None,  # Step 6.2 加入耗时
                "error": n.error,
            }
            for n in graph.nodes
        ]
        self._event_bus.publish(
            DashboardEvent(
                type="task:update",
                task_id=graph.task_id,
                payload=TaskUpdatePayload(
                    task_id=graph.task_id,
                    state="DAG_RUNNING",
                    progress=0.0,  # DAG 进度由已完成节点占比计算
                    dag=dag_nodes,
                    timestamp=datetime.now(UTC).isoformat(),
                ).model_dump(),
            )
        )

    # ---- Step 5.1 DAG 执行方法 ----

    async def run_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        """DAG 入口：验证→拓扑排序→分层并发执行。

        Returns:
            {node_id: NodeStatus} 各节点最终状态
        """
        # 验证 DAG 合法性
        graph.validate_dag()
        layers = graph.topological_sort()
        logger.info(
            "dag_execution_start",
            task_id=graph.task_id,
            nodes=len(graph.nodes),
            layers=len(layers),
        )

        for layer_idx, layer in enumerate(layers):
            logger.info(
                "dag_layer_executing",
                task_id=graph.task_id,
                layer=layer_idx,
                node_count=len(layer),
            )
            await self._execute_layer(graph, layer)
            # 检查快速失败：若配置 fail_fast 且任何节点失败则终止
            if self._fail_fast and any(
                (n := graph.get_node(nid)) and n.status == NodeStatus.FAILED for nid in layer
            ):
                logger.warning("dag_fail_fast_abort", task_id=graph.task_id)
                break

        results = {n.id: n.status for n in graph.nodes}
        logger.info("dag_execution_complete", task_id=graph.task_id, results=results)
        return results

    async def resume_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        """从检查点恢复 DAG 执行。

        WHY 恢复：跳过 SUCCESS 节点，从 PENDING/FAILED 节点继续。
        FAILED 节点给予一次额外重试机会（重试计数重置）。
        """
        # 将 RUNNING 节点重置为 PENDING（崩溃前未完成）
        for node in graph.nodes:
            if node.status == NodeStatus.RUNNING:
                node.status = NodeStatus.PENDING
            elif node.status == NodeStatus.FAILED:
                # 失败节点给一次恢复机会
                node.retry_count = 0
                node.status = NodeStatus.PENDING

        logger.info("dag_resume", task_id=graph.task_id)
        return await self.run_dag(graph)

    async def _execute_layer(self, graph: TaskGraph, layer: list[str]) -> None:
        """并发执行一层中所有节点。

        Semaphore 控制最大并发数（PRD 风险 R1）。
        """
        sem = asyncio.Semaphore(self._max_concurrent)

        async def _run_one(nid: str) -> None:
            async with sem:
                node = graph.get_node(nid)
                if node is None:
                    return
                await self._execute_node_with_retry(graph, node)

        tasks = [_run_one(nid) for nid in layer]
        await asyncio.gather(*tasks)

    async def _execute_node_with_retry(self, graph: TaskGraph, node: GraphNode) -> None:
        """执行单个节点，含超时和重试（AC4）。

        重试最多 MAX_RETRIES_PER_NODE 次，全部失败后标记 FAILED。
        """
        node.status = NodeStatus.RUNNING
        await self._save_dag_checkpoint(graph)
        self._publish_dag_update(graph)

        for attempt in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_node(node), timeout=self._node_timeout
                )
                node.output = result
                node.status = NodeStatus.SUCCESS
                node.error = None
                await self._save_dag_checkpoint(graph)
                self._publish_dag_update(graph)
                return
            except TimeoutError:
                node.error = f"Timeout after {self._node_timeout}s (attempt {attempt+1})"
                logger.warning("dag_node_timeout", node=node.id, attempt=attempt + 1)
            except Exception as e:
                node.error = str(e)
                logger.warning("dag_node_failed", node=node.id, error=str(e))

            node.retry_count = attempt + 1

        # 所有重试耗尽
        node.status = NodeStatus.FAILED
        await self._save_dag_checkpoint(graph)
        self._publish_dag_update(graph)
        logger.error("dag_node_all_retries_exhausted", node=node.id)

    async def _execute_node(self, node: GraphNode) -> dict[str, Any]:
        """执行单个节点的 Agent 逻辑。

        WHY 可扩展：当前为占位实现（模拟 Agent 执行），
        Step 5.2 接入 AgentFactory 后根据 agent_role 路由到具体 Agent。
        """
        # MVP 占位：模拟执行延迟（10-50ms 随机）
        await asyncio.sleep(0.01)
        return {"status": "ok", "node": node.id, "role": node.agent_role}

    async def _save_dag_checkpoint(self, graph: TaskGraph) -> None:
        """保存 DAG 检查点（节点状态快照）。

        WHY 只保存状态不保存大对象：orjson 序列化快，完整代码等大对象
        由 Agent 层独立存储（PRD ADR 风险 R2）。
        """
        if self.checkpoint is None:
            return
        try:
            snapshot = {
                "task_id": graph.task_id,
                "nodes": [
                    {
                        "id": n.id,
                        "status": n.status.value,
                        "retry_count": n.retry_count,
                        "error": n.error,
                    }
                    for n in graph.nodes
                ],
            }
            data = CheckpointData(
                task_id=graph.task_id,
                state="DAG_RUNNING",
                retry_count=0,
                progress=0.0,
                context=snapshot,
                version=1,
            )
            await self.checkpoint.save(graph.task_id, data)
        except Exception as e:
            logger.warning("dag_checkpoint_save_failed", error=str(e))


def generate_task_id() -> str:
    """生成任务 ID（uuid4 hex，与 API 层一致）。

    WHY 保留为公共 API：调度器外部入口（API 层创建任务/CLI 工具）可能复用，
    当前 API 层独立生成 ID，此方法供测试和未来 CLI 用。

    WHY 模块级函数不用 @staticmethod：此函数不在类内，@staticmethod 是 Python
    no-op（无实际效果），mypy 报 misc 错误。零外部调用方，删除不影响 API。
    """
    return uuid.uuid4().hex
