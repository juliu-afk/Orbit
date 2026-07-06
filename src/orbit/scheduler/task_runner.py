"""TaskRunner——单任务生命周期执行器（内部减熵 P1）.

从 Scheduler 拆出: run_task / _agent_cycle / _run_agent / _build_context /
save_checkpoint / resume / _continue_from.
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

from orbit.agents.base import AgentInput
from orbit.agents.context import ContextStage, TaskContext
from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload
from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore
from orbit.scheduler.complexity import ComplexityScorer
from orbit.scheduler.edit_stability import EditStabilityDetector

logger = structlog.get_logger("orbit.scheduler.runner")

# 状态→角色映射（从 Scheduler._agent_cycle 移出）
ROLE_MAP: dict[TaskState, str] = {
    TaskState.IDLE: "chatter",  # 首触点——通用对话，检测到编程意图后路由到 clarifier
    TaskState.PARSING: "clarifier",
    TaskState.SCOPING: "__scoping__",  # Phase 2 Token节省: 变更范围分析（规则引擎，非LLM）
    TaskState.PLANNING: "architect",
    TaskState.CODING: "developer",
    TaskState.VERIFYING: "reviewer",
}

# Inkeep 借鉴 #1: TaskState → task_type 映射（三层模型路由）
_TASK_TYPE_MAP: dict[TaskState, str] = {
    TaskState.IDLE: "summarization",              # 闲聊/首触点
    TaskState.PARSING: "structured_output",       # 需求解析需结构化输出
    TaskState.SCOPING: "summarization",           # Phase 2: 规则引擎——不需要 LLM 推理
    TaskState.PLANNING: "reasoning",              # 架构设计需最强推理
    TaskState.CODING: "reasoning",                # 代码生成需推理
    TaskState.VERIFYING: "structured_output",     # 审查结果结构化
}

TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}

# ── CUA-US1: Agent 循环鲁棒性配置（来源：OpenAI CUA Sample App responses-loop.ts）──
# WHY Agent 步骤超时：每个状态对应一次完整 Agent 执行（含 LLM API 调用），
# 不是单个 tool call 超时。默认 120s——GLM-5 reasoning 调用 10-40s，留足余量。
# CODING 状态用 180s（代码生成最耗时），其他用 120s。
# REVIEW-FIX P0-1: 原值 20s/60s 过短——PLANNING 架构推理 40s+ 几乎必然超时。
AGENT_STEP_TIMEOUT_SECONDS: dict[TaskState, int] = {
    TaskState.CODING: 180,
    TaskState.SCOPING: 30,  # Phase 2: 规则引擎——git diff + AST 扫描很快
}
AGENT_STEP_TIMEOUT_DEFAULT = 120

# WHY 动作间延迟 120ms：OpenAI CUA 动作间延迟模拟人类操作节奏，防止 DOM/文件系统
# 渲染追赶不上。Orbit 在写文件→跑测试等关键转换间插入延迟，防止文件系统未刷盘。
ACTION_DEBOUNCE_SECONDS = 0.12

# WHY 循环上限 50 轮：OpenAI CUA 默认 24 轮可配。Orbit 任务更复杂，设 50 轮硬上限，
# 防止 Agent 死循环。超限 → FAILED + audit 记录。
MAX_AGENT_CYCLES = 50

# 需要防抖延迟的状态转换（写文件后→验证前）
_DEBOUNCE_TRANSITIONS: set[tuple[TaskState, TaskState]] = {
    (TaskState.CODING, TaskState.VERIFYING),
}


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
        agent_llms: dict[str, LLMClient] | None = None,
        checkpoint: CheckpointManager | None = None,
        event_bus: EventBus | None = None,
        compressor: ContextCompressor | None = None,
        budget_tracker: TokenBudgetTracker | None = None,  # P1-4: budget_tracker 注入
        tool_registry: ToolRegistry | None = None,
        audit_logger: AuditLogger | None = None,
        router: IntakeRouter | None = None,
        graph: CodeGraphEngine | None = None,  # G2: 图谱引擎——Stage 2 符号查询
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
        self._graph = graph  # G2: 图谱引擎
        self._fast_lane = fast_lane
        # 减熵闭环-2: 编辑摇摆检测器（全局单例）
        self._edit_detector = EditStabilityDetector()
        # Phase F: 全模块集成接线器（懒初始化）
        self._wiring = None

    # ── 公共入口 ────────────────────────────────────────

    async def run_task(self, task_id: str, prd: str) -> TaskState:
        """运行单个任务：IDLE → ... → DONE/FAILED."""
        state = TaskState.IDLE
        await self._save_checkpoint(task_id, state, {"prd": prd})
        context: dict[str, Any] = {"prd": prd, "artifacts": {}, "mode": "auto"}
        # Phase F: 接线——任务开始
        # project_path 由上游 Scheduler 设置——未设置时传空，ProfileStore 跳过
        self._wire("on_task_start", task_id, prd[:100], project_id=context.get("project_path", ""))
        # 减熵闭环-2 B4: 检查目标文件编辑稳定性
        try:
            target_file = context.get("target_file", "")
            if target_file:
                report = self._edit_detector.check(target_file)
                if report.is_high_entropy:
                    logger.warning(
                        "high_entropy_file_detected", file=target_file, suggestion=report.suggestion
                    )
                    context["entropy_warning"] = report.suggestion
        except Exception:
            pass  # fail-open

        # 复杂度评估→决定快车道
        if context.get("mode") == "auto":

            scorer = ComplexityScorer()
            c_result = scorer.evaluate(prd)
            self._fast_lane = c_result.recommended_mode == "fast"
            context["complexity"] = c_result.to_dict()

        while state not in TERMINAL_STATES:
            try:
                # CUA-US1: 循环硬上限——防止 Agent 死循环
                cycle_count = context.get("_cycle_count", 0)
                cycle_count += 1
                context["_cycle_count"] = cycle_count
                if cycle_count > MAX_AGENT_CYCLES:
                    logger.error(
                        "max_cycles_exceeded",
                        task_id=task_id,
                        cycles=cycle_count,
                        max_cycles=MAX_AGENT_CYCLES,
                    )
                    state = TaskState.FAILED
                    context["error"] = f"max_cycles_exceeded: {cycle_count} > {MAX_AGENT_CYCLES}"
                    await self._save_checkpoint(task_id, state, context)
                    if self._audit_logger:
                        self._audit_logger.log(
                            "task_runner", "max_cycles_exceeded",
                            task_id=task_id, status="error",
                            detail={"cycles": cycle_count, "max": MAX_AGENT_CYCLES},
                        )
                    return state

                # CUA-US1: CODING 状态强制串行化——防止并发编辑冲突
                if state == TaskState.CODING:
                    context["parallel_tool_calls"] = False

                observation = await self._agent_cycle(task_id, state, context)
                context["artifacts"][state.value] = observation
                self._publish_task_update(
                    task_id, state.value, _state_to_progress(state), context=context
                )

                prev_state = state

                # Phase F: 接线——记录状态变迁事件
                if prev_state == TaskState.CODING and observation:
                    self._wire("record_event", task_id, f"CODING完成", "success" if "error" not in str(observation)[:200].lower() else "failure", category="编码")

                    # v0.21: CODING 完成后跑全量防幻觉验证 (L1-L8)
                    # WHY: validate_quick() 仅在 react_agent 工具调用后跑 L1+L3+L4，
                    # validate_full() 跑全部 8 层——commit 级别的完整检查。
                    try:
                        from orbit.hallucination.pipeline import HallucinationPipeline  # noqa: F811
                        pipeline = HallucinationPipeline()
                        full_result = await pipeline.validate_full(str(observation))
                        if not full_result.passed:
                            logger.warning(
                                "hallucination_full_failed",
                                task_id=task_id,
                                errors=full_result.errors[:5],
                            )
                            context.setdefault("l2", {})["hallucination_full"] = {
                                "passed": False,
                                "errors": full_result.errors[:10],
                            }
                        else:
                            context.setdefault("l2", {})["hallucination_full"] = {"passed": True}
                    except Exception:
                        logger.debug("hallucination_full_skipped", task_id=task_id)

                # 意图路由: IDLE 状态由 chatter 接管——
                # chat → 结束, programming → 正常进入 PARSING
                if state == TaskState.IDLE and context.get("chatter_intent") == "chat":
                    state = TaskState.DONE
                    logger.info("task_chat_complete", task_id=task_id)
                else:
                    state = _transition(state, self._fast_lane)

                # CUA-US1: 关键状态转换间插入防抖延迟
                if (prev_state, state) in _DEBOUNCE_TRANSITIONS:
                    await asyncio.sleep(ACTION_DEBOUNCE_SECONDS)

                await self._save_checkpoint(task_id, state, context)
            except asyncio.CancelledError:
                raise  # P0-1: 不吞取消信号，保持协作式取消语义
            except Exception as e:
                logger.error("task_failed", task_id=task_id, state=state.value, error=str(e))
                state = TaskState.FAILED
                await self._save_checkpoint(task_id, state, {**context, "error": str(e)})
                self._wire("on_task_end", task_id, "failed", 0.0, turns=cycle_count)
                return state

        # Phase F: 接线——任务完成 + 周期蒸馏
        self._wire("on_task_end", task_id, "completed" if state == TaskState.DONE else str(state.value), 0.8, turns=cycle_count)
        try:
            w = self._get_wiring()
            if w: asyncio.create_task(w.maybe_distill())
        except Exception: pass
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
        # REVIEW-FIX P1-5: resume 时重置循环计数器，
        # 避免 checkpoint 中的旧计数导致 resume 后立即触发上限。
        context["_cycle_count"] = 0
        return await self._continue_from(task_id, state, context)

    # ── Agent 循环 ──────────────────────────────────────

    async def _agent_cycle(self, task_id: str, state: TaskState, context: dict[str, Any]) -> str:
        """单个 Agent 循环——按状态映射角色→拉起 Agent 执行.

        IDLE 状态特殊处理: chatter agent 返回 _intent 标记，
        "chat" → 结束任务, "programming" → 继续进入 PARSING (clarifier).

        G1 (grill-me): 加载 Mode 配置，注入到 Agent 行为层。
        """
        role = ROLE_MAP.get(state)

        # Phase 2 Token节省: SCOPING 走规则引擎——非 LLM Agent
        if role == "__scoping__":
            return await self._run_scoping(task_id, context)

        if role and self._agent_factory is not None:
            context["state"] = state.value
            context["agent_name"] = role
            # Inkeep 借鉴 #1: 注入 task_type 供 Agent 选择模型
            task_type = _TASK_TYPE_MAP.get(state, "reasoning")
            context["task_type"] = task_type

            # G1: 加载 Mode 配置——用于 Agent 行为注入
            # 加载失败降级到 None → Agent 使用内置默认行为
            mode = None
            try:
                from orbit.modes.loader import ModeLoader  # noqa: F811
                loader = ModeLoader()
                mode = loader.resolve_for_state(state.value)
                if mode:
                    logger.debug("mode_loaded_for_state", state=state.value, mode=mode.name)
            except Exception:
                logger.debug("mode_load_skipped", state=state.value)
            context["_mode"] = mode  # 透传给 _run_agent

            # CUA-US1: 注入 Agent 步骤超时——CODING 180s，其他 120s
            step_timeout = AGENT_STEP_TIMEOUT_SECONDS.get(state, AGENT_STEP_TIMEOUT_DEFAULT)
            context["agent_step_timeout"] = step_timeout

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

            result = await self._run_agent(role, task_id, context)

            # IDLE + chatter: 提取意图标记用于路由决策
            if state == TaskState.IDLE and role == "chatter":
                intent = self._extract_chatter_intent(result)
                context["chatter_intent"] = intent
                logger.info(
                    "chatter_intent_detected",
                    task_id=task_id,
                    intent=intent,
                )

            return result

        raise RuntimeError(f"状态 {state.value} 无 Agent 角色映射，Orbit 不支持直接 LLM 调用。")

    @staticmethod
    def _extract_chatter_intent(output: str) -> str:
        """从 chatter agent 输出中提取意图标记。"""
        import json as _json
        import re as _re

        try:
            data = _json.loads(output)
            return data.get("_intent", "chat")
        except (_json.JSONDecodeError, ValueError, TypeError):
            pass
        # REVIEW-FIX: 原 regex "__?intent__?" 要求 intent 前后均有 _，
        # 不匹配 "_intent"（仅前缀有 _）。改为 _{0,2} 使前后 _ 均可选。
        match = _re.search(r'"_{0,2}intent_{0,2}"\s*:\s*"(chat|programming)"', output)
        if match:
            return match.group(1)
        return "chat"

    async def _run_scoping(self, task_id: str, context: dict[str, Any]) -> str:
        """SCOPING 状态——确定性变更范围分析 (Phase 2 Token节省).

        纯规则引擎——git diff + Python AST，0 LLM 调用。
        输出变更范围报告，决定后续测试粒度。
        fail-open: 任何异常返回 generic 报告，不阻塞任务。
        """
        import json as _json

        try:
            from orbit.context.scanners.affected_files import AffectedFilesScanner
            from orbit.context.scanners.import_deps import ImportDependencyScanner
        except ImportError:
            logger.warning("scoping_scanner_import_failed", task_id=task_id)
            return _json.dumps({"test_scope": "unit_integration", "note": "scanner_unavailable"})

        project_path = context.get("project_path", ".")
        scope_report: dict[str, Any] = {}

        # 扫描 1: git diff → 受影响文件
        try:
            af_scanner = AffectedFilesScanner()
            scope_report["affected_files"] = af_scanner.scan(project_path)
        except Exception as e:
            logger.warning("scoping_affected_files_failed", error=str(e))
            scope_report["affected_files"] = {"error": str(e), "total": 0}

        # 扫描 2: Python AST → import 依赖
        try:
            deps_scanner = ImportDependencyScanner()
            affected = scope_report.get("affected_files", {})
            changed = affected.get("changed", []) + affected.get("added", [])
            scope_report["import_deps"] = deps_scanner.scan(project_path, affected_files=changed)
        except Exception as e:
            logger.warning("scoping_import_deps_failed", error=str(e))
            scope_report["import_deps"] = {"error": str(e)}

        # 决策测试粒度
        affected = scope_report.get("affected_files", {})
        scope_report["test_scope"] = _decide_test_scope(affected)

        context["scope_report"] = scope_report
        # 注入 L2——供 Architect/Developer/Reviewer/QA 消费
        context.setdefault("l2", {})["scope_report"] = scope_report

        # v0.21: 接入 Context Builder 链——消费 scope_report 产出多维度上下文
        # WHY: PR #201 新增 9 个 Builder 但从未集成——scoping 后有结构化数据可消费
        try:
            from orbit.context.builders import build_all

            builder_inputs: dict[str, Any] = {
                "prd": context.get("prd", ""),
                "brief": context.get("brief", ""),
                "project_root": project_path,
                "affected_files": scope_report.get("affected_files", {}),
                "import_deps": scope_report.get("import_deps", {}),
                "test_scope": scope_report.get("test_scope", "unit_integration"),
                "keywords": context.get("keywords", []),
                "design": scope_report.get("design", {}),
            }
            builder_output = build_all(builder_inputs)
            scope_report["builder_context"] = builder_output
            context.setdefault("l2", {})["builder_context"] = builder_output
            logger.debug(
                "context_builders_complete",
                task_id=task_id,
                builders=len(builder_output),
            )
        except Exception:
            logger.debug("context_builders_failed", task_id=task_id)

        logger.info(
            "scoping_complete",
            task_id=task_id,
            files=affected.get("total", 0),
            test_scope=scope_report["test_scope"],
        )
        return _json.dumps(scope_report)

    async def _run_agent(
        self, role: str, task_id: str, context: dict[str, Any], timeout: int | None = None
    ) -> str:
        """拉起 Agent 协程——AgentFactory 创建 + 注入依赖 + 超时保护.

        CUA-US1: timeout 按状态分级——CODING 180s，其他 120s。
        可通过 context['agent_step_timeout'] 覆盖。
        REVIEW-FIX P0-1: 从 _agent_cycle 调用时默认 None → 读 context 超时配置。
        timeout 包裹整个 agent.execute()（含 LLM API），非单个 tool call。
        """
        t_start = time.monotonic()
        if self._agent_factory is None:
            raise RuntimeError("AgentFactory 未配置")

        # CUA-US1: Agent 步骤超时——按任务状态取不同阈值
        if timeout is None:
            timeout = context.get("agent_step_timeout", AGENT_STEP_TIMEOUT_DEFAULT)

        agent_llm = self._agent_llms.get(role) if self._agent_llms else None

        # 减熵闭环-1: 从 PRD 提取关键词 → 激活 B1/B3/B5
        prd_text = context.get("prd", "")
        task_keywords = self._extract_keywords(prd_text)
        try:
            # G1: 从 context 提取 mode 配置（_agent_cycle 中加载）
            mode = context.get("_mode")
            agent = self._agent_factory.create(
                role,
                llm=agent_llm,
                compressor=self._compressor,
                budget_tracker=self._budget_tracker,
                task_keywords=task_keywords,  # 减熵闭环-1
                mode=mode,  # G1: grill-me Mode File System
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

        # Phase 2 Token节省: 前置 context 裁剪——确定性预处理，节省 LLM token
        # fail-open: 裁剪失败不阻塞 Agent 执行
        try:
            from orbit.context.prebuilder import ContextPrebuilder
            prebuilder = ContextPrebuilder.build_for_role(role)
            pruned = prebuilder.build(agent_context.to_dict())
            # G2: 保存 stage——重建时 stage 是运行时状态，不应被 prebuilder 覆盖
            saved_stage = getattr(agent_context, "stage", None)
            # 重建 TaskContext——保持 to_dict() 截断能力
            agent_context = type(agent_context)(**{
                k: v for k, v in pruned.items()
                if k in {f.name for f in type(agent_context).__dataclass_fields__.values()}
            })
            if saved_stage is not None:
                agent_context.stage = saved_stage
        except Exception:
            logger.debug("prebuilder_failed_fail_open", role=role, exc_info=True)

        if self._audit_logger:
            self._audit_logger.log("orchestrator", "agent_start", task_id=task_id, role=role)

        try:
            try:
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
                # G2: Agent 失败→自动升级上下文阶段 (Stage 1→2)，给 Agent 更多信息重试
                # 每任务只升级一次——load_stage() 内部有 _stage_upgraded 标记
                mode_config = context.get("_mode")
                auto_upgrade = (
                    mode_config is not None
                    and mode_config.behavior.auto_upgrade_context
                )
                if auto_upgrade and hasattr(agent_context, "load_stage"):
                    try:
                        # 构建 MemoryStore 供 load_stage 使用
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
                logger.error("agent_run_error", role=role, task_id=task_id, error=str(e))
                if self._audit_logger:
                    self._audit_logger.log(
                        "orchestrator", "agent_run_error", task_id=task_id, role=role, error=str(e)
                    )
                raise

            # 减熵闭环-2 B4: 记录文件编辑
            try:
                target_file = context.get("target_file", "")
                if target_file and role:
                    self._edit_detector.record_edit(target_file, agent_id=role)
            except Exception:
                pass  # fail-open

            return str(output)
        finally:
            elapsed = time.monotonic() - t_start
            from orbit.observability.metrics import record_scheduling_latency

            record_scheduling_latency("dispatch_task", elapsed)

    def _build_context(self, task_id: str, context: dict[str, Any]) -> Any:
        """构建 L1-L5 TaskContext——G2 渐进式: 默认仅 Stage 1.

        WHY 渐进式: grill-me 模式——先给最少上下文，失败/不确定时再升级。
        Stage 1: L1+L3 核心字段 ~2K tokens（始终构建）。
        Stage 2: L2+L4 图谱+工作记忆（_run_agent 失败时 ctx.load_stage()）。
        Stage 3: L5 长期记忆（Agent 显式请求时）。
        """
        # G2: Stage 1 只构建 L1+L3——L2/L4/L5 延迟到 load_stage()
        # fast_lane 任务不会触发 Stage 2+，省 60-80% token
        return TaskContext(
            task_id=task_id,
            agent_name=context.get("agent_name", ""),
            model_tier=context.get("model_tier", ""),
            l1="遵循小企业会计准则; 禁止直接操作总账; 金额使用 Decimal",
            l2={},  # G2: 延迟到 Stage 2
            l3={
                "state": context.get("state", "UNKNOWN"),
                "prd": context.get("prd", ""),
                "artifacts": context.get("artifacts", {}),
            },
            l4={},  # G2: 延迟到 Stage 2
            l5=[],  # G2: 延迟到 Stage 3
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

    @staticmethod
    def _extract_keywords(prd_text: str) -> list[str]:
        """从 PRD 文本提取技术关键词——减熵闭环-1.

        简单分词 + 停用词过滤 + 标识符保留。零外部依赖。
        供 B1(上下文裁剪)/B3(模板库)/B5(决策日志) 使用。
        """
        if not prd_text:
            return []

        # 中文停用词——高频虚词
        _stop = {
            "的",
            "是",
            "在",
            "和",
            "了",
            "有",
            "不",
            "我",
            "我们",
            "要",
            "可以",
            "这个",
            "那个",
            "一个",
            "一些",
            "需要",
            "应该",
            "能够",
            "使用",
            "通过",
            "进行",
            "实现",
            "添加",
            "修改",
            "删除",
            "支持",
            "提供",
            "包括",
            "用于",
            "the",
            "a",
            "an",
            "is",
            "are",
            "be",
            "to",
            "of",
            "in",
            "for",
            "and",
            "or",
            "not",
            "this",
            "that",
            "with",
            "from",
            "will",
            "can",
            "should",
            "it",
            "we",
            "you",
            "as",
            "if",
            "but",
            "so",
            "all",
            "no",
            "on",
            "at",
        }

        # 技术关键词——CamelCase/snake_case/中文技术词
        keywords: list[str] = []
        # 1. 提取英文标识符（CamelCase/snake_case）
        for word in prd_text.replace("\n", " ").split():
            word = word.strip(".,;:()[]{}<>\"'`/\\|!@#$%^&*+-=~")
            if len(word) < 2:
                continue
            # 标识符模式：含大写字母或下划线
            if any(c.isupper() for c in word) or "_" in word:
                if word.lower() not in _stop:
                    keywords.append(word)
        # 2. 提取中文技术词（2-6 个汉字）
        import re as _re

        cn_terms = _re.findall(r"[一-鿿]{2,6}", prd_text)
        for t in cn_terms:
            if t not in _stop and t not in keywords:
                keywords.append(t)
        # 去重 + 限制数量
        seen: set[str] = set()
        uniq = []
        for k in keywords:
            if k.lower() not in seen:
                seen.add(k.lower())
                uniq.append(k)
        # 最多 20 个关键词，避免 prompt 膨胀
        return uniq[:20]

    # Phase F: 接线辅助方法
    def _wire(self, method: str, *args, **kwargs) -> None:
        """调用 OrbitWiring 方法——fail-open。"""
        try:
            w = self._get_wiring()
            if w: getattr(w, method)(*args, **kwargs)
        except Exception: pass

    def _get_wiring(self):
        if self._wiring is None:
            try:
                from orbit.integration.wiring import OrbitWiring
                self._wiring = OrbitWiring()
            except Exception: pass
        return self._wiring


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

# ── 状态流转图 (ChatterAgent 意图路由 + Phase 2 SCOPING) ─────────────────
# IDLE(chatter) → chat intent → DONE
# IDLE(chatter) → programming intent → PARSING(clarifier) → SCOPING(规则引擎) → PLANNING(architect) → CODING(developer) → VERIFYING(reviewer) → DONE
# 快车道: PARSING → CODING → DONE（跳过 SCOPING+PLANNING）


def _decide_test_scope(affected: dict[str, Any]) -> str:
    """变更范围 → 测试粒度决策 (Phase 2 Token节省).

    WHY 确定性规则而非 LLM: 文件路径 → 测试粒度的映射是机械的，
    不需要推理能力。LLM 判断反而慢且不稳定。

    规则:
      - 0 文件或无变更 → "smoke"
      - 仅 frontend/ → "smoke"
      - 触及核心模块 → "full_regression"
      - 其他 → "unit_integration"
    """
    files: list[str] = affected.get("changed", []) + affected.get("added", [])
    if not files:
        return "smoke"

    # 核心模块——改动影响面大，需全量回归
    _core_modules = {
        "src/orbit/agents/",
        "src/orbit/scheduler/",
        "src/orbit/gateway/",
        "src/orbit/compression/",
        "src/orbit/hallucination/",
        "src/orbit/checkpoint/",
        "src/orbit/sandbox/",
    }
    if any(any(f.startswith(m) for m in _core_modules) for f in files):
        return "full_regression"

    # 纯前端变更——冒烟够用
    if all(f.startswith("frontend/") for f in files):
        return "smoke"

    return "unit_integration"
