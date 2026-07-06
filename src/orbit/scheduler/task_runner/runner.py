"""TaskRunner——单任务生命周期执行器。

从 task_runner.py 拆分——上下文构建见 context.py，检查点见 checkpoint.py，
共享工具函数见 __init__.py。
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orbit.agents.factory import AgentFactory
    from orbit.compression.budget import TokenBudgetTracker
    from orbit.compression.compressor import ContextCompressor
    from orbit.gateway.client import LLMClient
    from orbit.goal.intake_router import IntakeRouter
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.observability.audit import AuditLogger
    from orbit.tools.registry import ToolRegistry

import structlog

from orbit.agents.base import AgentInput, AgentRole
from orbit.agents.context import ContextStage, TaskContext
from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.scheduler.task_runner.checkpoint import (
    FAST_LANE_TRANSITIONS,
    STATE_TRANSITIONS,
    _state_to_progress,
    _transition,
)
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload
from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore
from orbit.scheduler.complexity import ComplexityScorer
from orbit.scheduler.edit_stability import EditStabilityDetector
from orbit.scheduler.task_runner.checkpoint import (
    TaskCheckpointMixin,
    _state_to_progress,
)
from orbit.scheduler.task_runner.context import TaskContextMixin

logger = structlog.get_logger("orbit.scheduler.runner")

# 状态→角色映射（从 Scheduler._agent_cycle 移出）
ROLE_MAP: dict[TaskState, str] = {
    TaskState.IDLE: "chatter",
    TaskState.PARSING: "clarifier",
    TaskState.SCOPING: "__scoping__",
    TaskState.PLANNING: "architect",
    TaskState.CODING: "developer",
    TaskState.VERIFYING: "reviewer",
}

# Inkeep 借鉴 #1: TaskState → task_type 映射（三层模型路由）
_TASK_TYPE_MAP: dict[TaskState, str] = {
    TaskState.IDLE: "summarization",
    TaskState.PARSING: "structured_output",
    TaskState.SCOPING: "summarization",
    TaskState.PLANNING: "reasoning",
    TaskState.CODING: "reasoning",
    TaskState.VERIFYING: "structured_output",
}

TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}

# ── CUA-US1: Agent 循环鲁棒性配置 ──
AGENT_STEP_TIMEOUT_SECONDS: dict[TaskState, int] = {
    TaskState.CODING: 180,
    TaskState.SCOPING: 30,
}
AGENT_STEP_TIMEOUT_DEFAULT = 120
ACTION_DEBOUNCE_SECONDS = 0.12
MAX_AGENT_CYCLES = 50


class TaskRunner(TaskContextMixin, TaskCheckpointMixin):
    """单任务生命周期执行器。

    从 Scheduler 拆出——run_task / _agent_cycle / _run_agent /
    _build_context / save_checkpoint / resume / _continue_from。
    """

    def __init__(
        self,
        agent_llms: dict[str, LLMClient] | None = None,
        checkpoint: CheckpointManager | None = None,
        graph: CodeGraphEngine | None = None,
        agent_factory: AgentFactory | None = None,
        event_bus: EventBus | None = None,
        complexity_scorer: ComplexityScorer | None = None,
        compressor: ContextCompressor | None = None,
        budget_tracker: TokenBudgetTracker | None = None,
        router: IntakeRouter | None = None,
        audit_logger: AuditLogger | None = None,
        fast_lane: bool = False,
        tool_registry: ToolRegistry | None = None,
    ):
        self._agent_llms = agent_llms or {}
        self.checkpoint = checkpoint
        self._graph = graph
        self._agent_factory = agent_factory
        self._event_bus = event_bus
        self._complexity_scorer = complexity_scorer
        self._compressor = compressor
        self._budget_tracker = budget_tracker
        self._router = router
        self._audit_logger = audit_logger
        self._fast_lane = fast_lane
        self._tool_registry = tool_registry
        self._edit_detector = EditStabilityDetector()

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        """入口——从 IDLE 开始执行完整任务管线."""
        context: dict[str, Any] = {"prd": prd}
        state = TaskState.IDLE

        # 复杂度评分——决定 fast_lane
        if self._complexity_scorer:
            score = self._complexity_scorer.score(prd)
            context["complexity_score"] = score
            self._fast_lane = score.is_trivial

        state = _transition(state, self._fast_lane)
        await self._save_checkpoint(task_id, state, context)

        # v0.21: 提取 PRD 关键词——供整个任务管线使用
        keywords = self._extract_keywords(prd)
        context["keywords"] = keywords

        # Phase F: 接线——任务开始 + 轨迹 + 用户画像
        # WHY fail-open: 接线模块是可选的——失败不阻塞任务执行
        try:
            from orbit.integration.wiring import get_wiring
            w = get_wiring()
            if w:
                project_id = context.get("project_id", "")
                w.on_task_start(task_id, prd, project_id=project_id)
                # 加载用户画像
                if project_id:
                    try:
                        profile = w.load_profile(project_id)
                        if profile:
                            context["user_profile"] = profile
                    except Exception:
                        pass
                # 异步启动监控——不阻塞任务管线
                try:
                    asyncio.create_task(
                        w.start_monitor(task_id, goal=prd[:200])
                    )
                except Exception:
                    pass
        except Exception:
            pass

        cycle_count = 0
        while state not in TERMINAL_STATES:
            # 检查是否已取消
            observation = await self._agent_cycle(task_id, state, context)
            context.setdefault("artifacts", {})[state.value] = observation
            state = _transition(state, self._fast_lane)
            await self._save_checkpoint(task_id, state, context)

            # CUA-US1: 循环上限——防止 Agent 死循环
            cycle_count += 1
            if cycle_count >= MAX_AGENT_CYCLES:
                logger.error("max_cycles_exceeded", task_id=task_id, cycles=cycle_count)
                state = TaskState.FAILED
                context["error"] = "超过最大循环次数"
                await self._save_checkpoint(task_id, state, context)
                break

            # Phase 2: 压缩管线——token budget check
            if self._budget_tracker:
                try:
                    self._budget_tracker.check_and_warn()
                except Exception:
                    pass

        # 发布最终事件
        self._publish_task_update(
            task_id,
            state.value,
            100.0 if state == TaskState.DONE else 0.0,
            context=context,
        )

        # Phase F: 接线——任务完成 + 周期蒸馏
        try:
            from orbit.integration.wiring import get_wiring
            get_wiring().on_task_end(task_id,
                   "completed" if state == TaskState.DONE else str(state.value),
                   0.8, turns=cycle_count)
        except Exception:
            pass
        try:
            w = get_wiring()
            if w:
                asyncio.create_task(w.maybe_distill())
        except Exception:
            logger.warning("distill_schedule_failed", exc_info=True)
        return state

    async def resume(self, task_id: str) -> TaskState | None:
        """从检查点恢复任务."""
        if self.checkpoint is None:
            return None
        data = await self.checkpoint.load(task_id)
        if data is None:
            return None
        state = TaskState(data.state)
        context = data.context
        return await self._continue_from(task_id, state, context)

    async def _agent_cycle(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> str:
        """单轮 Agent 循环——选角色→运行→返回观察结果."""
        role = ROLE_MAP.get(state)
        if role is None:
            raise ValueError(f"未知状态无对应角色: {state}")

        # SCOPING 状态——确定性规则引擎，不调 LLM
        if state == TaskState.SCOPING:
            return await self._run_scoping(task_id, context)

        # 注入 task_type 用于模型路由
        task_type = _TASK_TYPE_MAP.get(state)
        if task_type:
            context["task_type"] = task_type
        # 注入当前状态供 Agent 使用
        context["state"] = state.value

        # 构建上下文
        agent_context = self._build_context(task_id, context)
        if self._audit_logger:
            self._audit_logger.log("orchestrator", "agent_start",
                                   task_id=task_id, role=role)

        try:
            ctx_dict = (
                agent_context.to_dict()
                if hasattr(agent_context, "to_dict")
                else {}
            )
            agent_input = AgentInput(
                task=ctx_dict.get("l3", {}).get("prd", ""),
                context=ctx_dict,
                role=AgentRole(role),
            )
            output_obj = await asyncio.wait_for(
                self._run_agent(role, task_id, context),
                timeout=AGENT_STEP_TIMEOUT_SECONDS.get(state, AGENT_STEP_TIMEOUT_DEFAULT),
            )
            if output_obj and hasattr(output_obj, "status") and output_obj.status == "ok":
                r = output_obj.result
                output = r.get("design") or r.get("code") or r.get("review") or str(r)
            else:
                err = getattr(output_obj, "error", "unknown") if output_obj else "null output"
                raise RuntimeError(f"Agent {role} 返回错误: {err}")
        except TimeoutError:
            logger.warning("agent_timeout", role=role, task_id=task_id)
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # 自动升级上下文
            mode_config = context.get("_mode")
            auto_upgrade = (
                mode_config is not None
                and mode_config.behavior.auto_upgrade_context
            )
            if auto_upgrade and hasattr(agent_context, "load_stage"):
                try:
                    project_path = context.get("project_path", "")
                    store = MemoryStore(project_path=project_path)
                    await agent_context.load_stage(
                        ContextStage.STAGE2,
                        graph=self._graph,
                        memory_store=store,
                    )
                    logger.info("context_auto_upgraded", task_id=task_id, role=role,
                                reason=str(e)[:100])
                except Exception:
                    logger.debug("context_upgrade_failed", task_id=task_id)
            logger.error("agent_run_error", role=role, task_id=task_id, error=str(e))
            if self._audit_logger:
                self._audit_logger.log("orchestrator", "agent_run_error",
                                       task_id=task_id, role=role, error=str(e))
            raise

        # 记录文件编辑
        try:
            target_file = context.get("target_file", "")
            if target_file and role:
                self._edit_detector.record_edit(target_file, agent_id=role)
        except Exception:
            pass

        return str(output)

    @staticmethod
    def _extract_chatter_intent(output: str) -> str:
        """从 ChatterAgent 输出提取意图标记."""
        match = re.search(r"_intent:\s*(\w+)", output)
        if match:
            return match.group(1)
        return "chat"

    async def _run_agent(
        self,
        role: str,
        task_id: str,
        context: dict[str, Any],
        timeout: int | None = None,
    ) -> str:
        """拉起 Agent 协程——AgentFactory 创建 + 注入依赖 + 超时保护."""
        t_start = time.monotonic()
        if self._agent_factory is None:
            raise RuntimeError("AgentFactory 未配置")

        if timeout is None:
            timeout = context.get("agent_step_timeout", AGENT_STEP_TIMEOUT_DEFAULT)

        llm = self._agent_llms.get(role)
        if llm is None:
            fallback_llm = next(iter(self._agent_llms.values()), None) if self._agent_llms else None
            if fallback_llm:
                logger.warning("agent_llm_fallback", role=role, fallback=str(fallback_llm))
                llm = fallback_llm
            else:
                raise RuntimeError(f"角色 {role} 无可用 LLMClient")

        # Phase F: 创建五大能力引擎实例（fail-open: llm=None时各引擎内部skip）
        from orbit.agents.reflection import ReflectionEngine
        from orbit.agents.preact import PreActEngine
        from orbit.metacognition.vigil import VigilSelfHealer

        ref_engine = ReflectionEngine(llm=llm) if llm else None
        pre_engine = PreActEngine(llm=llm, tools=self._tool_registry) if llm and self._tool_registry else None
        vigil = VigilSelfHealer()

        agent = self._agent_factory.create(
            role,
            llm=llm,
            graph=self._graph,
            sandbox=None,
            tools=self._tool_registry,
            event_bus=self._event_bus,
            compressor=self._compressor,
            budget_tracker=self._budget_tracker,
            reflection_engine=ref_engine,   # Phase A: ReflAct
            preact_engine=pre_engine,       # Phase D: PreAct
            vigil_healer=vigil,             # Phase D: VIGIL
        )

        context["mode"] = getattr(agent, "_mode", None)
        if self._audit_logger:
            self._audit_logger.log(
                "orchestrator", "agent_start", task_id=task_id, role=role
            )

        agent_context = self._build_context(task_id, context)

        try:
            try:
                ctx_dict = (
                    agent_context.to_dict()
                    if hasattr(agent_context, "to_dict")
                    else {}
                )
                agent_input = AgentInput(
                    task=ctx_dict.get("l3", {}).get("prd", ""),
                    context=ctx_dict,
                    role=AgentRole(role),
                )
                output_obj = await asyncio.wait_for(
                    agent.execute(agent_input), timeout=timeout
                )
                if output_obj.status == "ok":
                    r = output_obj.result
                    output = r.get("design") or r.get("code") or r.get("review") or str(r)
                else:
                    raise RuntimeError(
                        f"Agent {role} 返回错误: {output_obj.error}"
                    )
            except TimeoutError:
                logger.warning("agent_timeout", role=role, task_id=task_id)
                raise
            except asyncio.CancelledError:
                raise
            except Exception as e:
                mode_config = context.get("_mode")
                auto_upgrade = (
                    mode_config is not None
                    and mode_config.behavior.auto_upgrade_context
                )
                if auto_upgrade and hasattr(agent_context, "load_stage"):
                    try:
                        project_path = context.get("project_path", "")
                        store = MemoryStore(project_path=project_path)
                        await agent_context.load_stage(
                            ContextStage.STAGE2,
                            graph=self._graph,
                            memory_store=store,
                        )
                        logger.info(
                            "context_auto_upgraded",
                            task_id=task_id,
                            role=role,
                            reason=str(e)[:100],
                        )
                    except Exception:
                        logger.debug("context_upgrade_failed", task_id=task_id)
                logger.error(
                    "agent_run_error", role=role, task_id=task_id, error=str(e)
                )
                if self._audit_logger:
                    self._audit_logger.log(
                        "orchestrator",
                        "agent_run_error",
                        task_id=task_id,
                        role=role,
                        error=str(e),
                    )
                raise

            try:
                target_file = context.get("target_file", "")
                if target_file and role:
                    self._edit_detector.record_edit(target_file, agent_id=role)
            except Exception:
                pass

            return str(output)
        finally:
            elapsed = time.monotonic() - t_start
            from orbit.observability.metrics import record_scheduling_latency

            record_scheduling_latency("dispatch_task", elapsed)
