"""MetaOrchestrator——Goal 级编排器。

v5 架构核心:
- Intake Router 智能判定输入形态
- DependencyAnalyzer 分析复数任务依赖
- 每个子任务独立 SubTaskSession（独立 128K 上下文）
- 子任务间通过 git merge commit 传递状态 —— 0 Token 开销
- 自主 PR 合入门禁: CritiqueAgent APPROVED + ExecutorVerifier 通过 + RegressionGuard 无回归
- Phase 3 组 2: Goal pause/resume——asyncio.Event 层间暂停
"""

from __future__ import annotations

import asyncio
import structlog
import time
from datetime import UTC, datetime

from orbit.goal.intake_router import IntakeRouter
from orbit.goal.memory_tiers import ThreeTierMemory
from orbit.observability.metrics import orbit_goal_status_total
from orbit.observability.trace import SpanStatus, TraceCollector
from typing import TYPE_CHECKING, Any

from orbit.goal.meta_utils import (
    _deserialize_spec,
    _generate_batch_report,
    _parse_to_goal,
    _resolve_bases,
    _topological_layers,
)
from orbit.goal.models import (
    GoalBatchReport,
    GoalResult,
    GoalSession,
    SubTaskResult,
)

if TYPE_CHECKING:
    from orbit.compose.models import Spec, Task
    from orbit.goal.alignment import AlignmentCheck
    from orbit.goal.budget_allocator import BudgetAllocator
    from orbit.goal.compose_bridge import GoalComposeBridge
    from orbit.goal.critique import CritiqueAgent
    from orbit.goal.dependency_analyzer import DependencyAnalyzer
    from orbit.goal.preflight import PreFlightEstimator
    from orbit.goal.progress_tracker import ProgressTracker
    from orbit.goal.regression_guard import RegressionGuard
    from orbit.goal.subtask_session import SubTaskSession
    from orbit.goal.verifier import ExecutorVerifier
    from orbit.worktree.manager import WorktreeManager

logger = structlog.get_logger("orbit.goal")


class AutoMergeRejected(Exception):
    """自主合入被拒绝——门禁未通过。"""

    def __init__(self, pr_id: str, reason: str) -> None:
        self.pr_id = pr_id
        self.reason = reason
        super().__init__(f"PR#{pr_id} 自主合入拒绝: {reason}")


class MetaOrchestrator:
    """Goal 级编排器。

    流程:
    0. Intake Router 判定 → 按需澄清/按需拆解
    1. (批量) DependencyAnalyzer → DAG 分层
    2. 逐层调度 SubTaskSession → 完整流水线
    3. 每个 SubTaskSession: CritiqueAgent → 验证 → 自主 PR 合入
    4. 每 5 Task: 对齐检查
    5. 全部完成: 全量回归 → 汇总报告
    """

    def __init__(
        self,
        intake_router: IntakeRouter | None = None,
        dependency_analyzer: DependencyAnalyzer | None = None,
        compose_bridge: GoalComposeBridge | None = None,
        clarifier: Any = None,  # ClarifierAgent
        progress_tracker: ProgressTracker | None = None,
        alignment_check: AlignmentCheck | None = None,
        regression_guard: RegressionGuard | None = None,
        memory: ThreeTierMemory | None = None,
        preflight: PreFlightEstimator | None = None,
        budget_allocator: BudgetAllocator | None = None,
        verifier: ExecutorVerifier | None = None,
        critique_agent: CritiqueAgent | None = None,
        compose_orchestrator: Any = None,  # ComposeOrchestrator
        ensemble: Any = None,  # ModelEnsemble
        worktree_manager: WorktreeManager | None = None,
        agent_factory: Any = None,  # AgentFactory
        max_parallel_tasks: int = 5,
    ) -> None:
        self.intake_router = intake_router or IntakeRouter()
        self.dependency_analyzer = dependency_analyzer
        self.compose_bridge = compose_bridge
        self.clarifier = clarifier
        self.progress_tracker = progress_tracker
        self.alignment_check = alignment_check
        self.regression_guard = regression_guard
        self.memory = memory or ThreeTierMemory()
        self.preflight = preflight
        self.budget_allocator = budget_allocator
        self.verifier = verifier
        self.critique_agent = critique_agent
        self.compose_orchestrator = compose_orchestrator
        self.ensemble = ensemble
        self._worktree = worktree_manager
        self._agent_factory = agent_factory
        self._max_parallel = max_parallel_tasks
        # Goal pause/resume——asyncio.Event 控制流暂停
        # WHY Event: set()=不阻塞(正常运行), clear()=阻塞(暂停中)
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始: 不暂停
        self._paused = False

    # ── 公共 API ──────────────────────────────────────

    def pause(self) -> None:
        """暂停当前 Goal——运行中的循环在下一个检查点阻塞。

        P2-2: 幂等——重复调用安全，已暂停时跳过。
        """
        if self._paused:
            return
        self._paused = True
        self._pause_event.clear()
        logger.info("meta_orchestrator_paused")

    def resume(self) -> None:
        """恢复已暂停的 Goal——解除检查点阻塞。

        P2-2: 幂等——重复调用安全，未暂停时跳过。
        """
        if not self._paused:
            return
        self._paused = False
        self._pause_event.set()
        logger.info("meta_orchestrator_resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def run(self, goal: GoalSession) -> GoalResult:
        """执行完整 Goal 生命周期。"""
        started_at = time.time()
        goal.started_at = datetime.now(UTC).isoformat()
        self._goal_started = started_at
        goal_span = TraceCollector.start_span(
            goal.id, component="orchestrator", action="schedule",
            input_summary=f"goal_desc={goal.description[:128] if goal.description else ''}",
        )
        self._current_goal_span = goal_span

        # 减熵闭环-3 B8: 自动生成 CLAUDE.md
        try:
            from orbit.knowledge.claude_md_generator import ClaudeMdGenerator

            gen = ClaudeMdGenerator()
            md_content = await gen.generate()
            if md_content:
                logger.info("claude_md_generated", length=len(md_content))
        except Exception:
            pass  # fail-open: 生成失败不影响任务执行

        try:
            # 阶段0: Intake Router
            decision = await self.intake_router.route(goal)

            # 复数文档→依赖分析+DAG调度
            if decision.is_batch:
                result = await self._run_batch(goal)
                self._record_goal_end(result.status)
                return result

            # 按需澄清
            if decision.needs_clarify and self.clarifier:
                goal = await self._clarify(goal)

            # V15.2: GoalPlanner——生成执行计划（独立于 compose_bridge）
            if decision.needs_decompose:
                plan = await self.intake_router.plan_for(
                    goal.description, goal.constraints
                )
                if plan:
                    logger.info(
                        "goal_plan_generated",
                        goal_id=goal.id,
                        milestones=len(plan.milestones),
                    )

            # 按需拆解
            if decision.needs_decompose and self.compose_bridge:
                if not goal.spec:
                    estimate = None
                    if self.preflight:
                        estimate = await self.preflight.estimate(goal.description)
                    spec = await self.compose_bridge.generate_spec(goal)
                    confirmed = await self._present_for_confirmation(estimate, spec, goal)
                    if not confirmed:
                        self._record_goal_end("cancelled")
                        return GoalResult(status="cancelled", reason="用户取消")
                    goal.spec = spec.model_dump() if hasattr(spec, "model_dump") else spec
                    goal.sub_tasks = {t.id: "pending" for t in spec.tasks}

            # 已有 TaskDAG→直接执行
            spec_data = goal.spec
            if not spec_data:
                # 无 spec 且无 compose_bridge——单任务模式
                result = await self._run_single_task(goal)
                self._record_goal_end(result.status)
                return result

            spec = _deserialize_spec(spec_data)

            # Goal→Compose: delegate to ComposeOrchestrator when available
            if self.compose_orchestrator:
                logger.info("goal_delegating_to_compose", goal_id=goal.id)
                compose_result = await self.compose_orchestrator.run_spec(
                    goal.description, parent_task_id=goal.id
                )
                elapsed = time.time() - started_at
                ok = compose_result.get("status") == "ok"
                status = "done" if ok else "partial"
                self._record_goal_end(status)
                return GoalResult(status=status, total_time_seconds=elapsed)

            layers = _topological_layers(spec.tasks)
            previous_merge_shas: dict[str, str] = {}

            # 阶段1: 分层调度
            completed_count = 0
            for layer_idx, layer in enumerate(layers):
                # 解析 base_ref
                task_bases = _resolve_bases(layer, previous_merge_shas)

                # 分配预算
                budgets = {}
                if self.budget_allocator:
                    budgets = self.budget_allocator.allocate(
                        layer, goal.total_token_budget - goal.token_consumed
                    )

                # 层内并行
                layer_results = await asyncio.gather(
                    *[
                        self._run_subtask(
                            t, task_bases.get(t.id, "main"), goal, budgets.get(t.id, 0)
                        )
                        for t in layer
                    ]
                )

                # 处理结果
                for task, result in zip(layer, layer_results):
                    goal.sub_tasks[task.id] = result.status if result.status == "ok" else "failed"
                    goal.token_consumed += result.tokens_used

                    if result.status == "ok":
                        previous_merge_shas[task.id] = result.merge_sha
                        # 回归守卫
                        if self.regression_guard:
                            await self.regression_guard.check()
                        completed_count += 1
                    elif result.status == "critique_loop":
                        self._record_goal_end("paused")
                        return GoalResult(
                            status="paused",
                            reason=f"Task {task.id} 批判退回超过上限",
                        )
                    else:
                        goal.consecutive_failures += 1
                        if goal.consecutive_failures >= 3:
                            self._record_goal_end("failed")
                            return GoalResult(
                                status="failed",
                                reason=f"连续 {goal.consecutive_failures} 个子任务失败",
                            )

                # 暂停检查点——在层间检查暂停信号
                await self._pause_event.wait()

                # 进度更新
                if self.progress_tracker:
                    await self.progress_tracker.update(goal)

                # 对齐检查（每 5 Task）
                if completed_count % 5 == 0 and self.alignment_check:
                    align = await self.alignment_check.check(goal, goal.sub_tasks)
                    if not align.aligned:
                        goal.consecutive_misalignments += 1
                        if goal.consecutive_misalignments >= 2:
                            self._record_goal_end("paused")
                            return GoalResult(status="paused", reason="连续 2 次对齐失败")
                    else:
                        goal.consecutive_misalignments = 0

                # 预算检查
                if self._budget_exhausted(goal):
                    self._record_goal_end("done")
                    return GoalResult(
                        status="done",
                        reason="预算耗尽",
                        tasks_completed=completed_count,
                    )

            # 汇总
            elapsed = time.time() - started_at
            self._record_goal_end("done")
            return GoalResult(
                status="done",
                tasks_completed=completed_count,
                total_tokens=goal.token_consumed,
                total_time_seconds=elapsed,
            )

        except asyncio.CancelledError:
            logger.info("meta_orchestrator_cancelled", goal_id=goal.id)
            raise
        except Exception as e:
            logger.error("meta_orchestrator_failed", goal_id=goal.id, error=str(e), exc_info=True)
            self._record_goal_end("failed")
            return GoalResult(
                status="failed",
                reason=str(e),
                total_time_seconds=time.time() - started_at,
            )

    # ── 内部: 子任务调度 ───────────────────────────────

    def _record_goal_end(self, status: str) -> None:
        """记录 Goal 终态指标 + 结束 trace span。"""
        orbit_goal_status_total.labels(status=status).inc()
        span = getattr(self, "_current_goal_span", None)
        if span is not None:
            _start = getattr(self, "_goal_started", 0.0)
            TraceCollector.end_span(
                span,
                status=SpanStatus.OK if status in ("done",) else SpanStatus.ERROR,
                output_summary=f"goal_{status}",
                duration_ms=(time.time() - _start) * 1000 if _start else None,
            )
            self._current_goal_span = None

    async def _run_subtask(
        self,
        task: Any,  # Task
        base_ref: str,
        goal: GoalSession,
        budget: int,
    ) -> SubTaskResult:
        """调度单个 SubTaskSession。"""
        from orbit.goal.subtask_session import SubTaskSession

        # 子任务独立 budget_tracker——避免共享导致上下文膨胀
        # WHY 独立 tracker: 每个 SubTaskSession 有独立 128K 上下文窗口，
        # 共享 tracker 会导致一个子任务耗尽预算后影响其他子任务
        budget_tracker = None
        if budget > 0:
            from orbit.compression.budget import TokenBudgetTracker

            budget_tracker = TokenBudgetTracker(max_context_window=budget)

        session = SubTaskSession(
            task=task,
            base_ref=base_ref,
            goal_context=self.memory.to_task_context(),
            goal=goal,
            agent_factory=self._agent_factory,
            worktree_manager=self._worktree,
            budget_tracker=budget_tracker,
            critique_agent=self.critique_agent,
            verifier=self.verifier,
        )
        return await session.run_full_pipeline()

    async def _run_single_task(self, goal: GoalSession) -> GoalResult:
        """单任务模式——无拆解，直接执行。

        v0.21: 接入 TaskShardingEngine——PRD > 8000 字符时分片并发执行。
        WHY: Sharding 引擎已在 PR #201 实现但从未集成到调度流程。
        """
        from orbit.compose.models import Task as ComposeTask

        # v0.21: 大 PRD 分片——按段落边界切分后并发执行子任务
        try:
            from orbit.sharding.engine import TaskShardingEngine

            engine = TaskShardingEngine()
            if engine.should_shard(goal.description):
                plan = engine.shard(goal.description, goal.id)
                logger.info(
                    "goal_sharding",
                    goal_id=goal.id,
                    shards=plan.total,
                    prd_chars=len(goal.description),
                )
                # 并发执行所有分片——复用 _run_subtask 管线
                results = await asyncio.gather(*[
                    self._run_subtask(
                        ComposeTask(id=s.shard_id, description=s.content),
                        "main",
                        goal,
                        goal.total_token_budget // max(plan.total, 1),
                    )
                    for s in plan.shards
                ])
                ok = sum(1 for r in results if r.status == "ok")
                failed = plan.total - ok
                total_tokens = sum(r.tokens_used for r in results)
                return GoalResult(
                    status="done" if failed == 0 else ("partial" if ok > 0 else "failed"),
                    tasks_completed=ok,
                    tasks_failed=failed,
                    total_tokens=total_tokens,
                )
        except ImportError:
            pass  # Sharding 引擎不可用——降级为单任务执行
        except Exception:
            logger.warning("sharding_failed_fallback_single", goal_id=goal.id)

        task = ComposeTask(id="task-0", description=goal.description)
        result = await self._run_subtask(task, "main", goal, goal.total_token_budget)
        return GoalResult(
            status="done" if result.status == "ok" else "failed",
            tasks_completed=1 if result.status == "ok" else 0,
            tasks_failed=0 if result.status == "ok" else 1,
            total_tokens=result.tokens_used,
        )

    async def _run_batch(self, goal: GoalSession) -> GoalResult:
        """批量模式——DependencyAnalyzer + 队列执行。"""
        batch_goals = goal.three_tier_memory.get("batch_goals", [])
        if not batch_goals:
            return GoalResult(status="failed", reason="批量模式下无有效 Goal")

        # 每个文档转为 GoalSession
        goals = [_parse_to_goal(doc) for doc in batch_goals]

        # 依赖分析
        dag = {}
        if self.dependency_analyzer:
            dag = await self.dependency_analyzer.analyze(goals)
            layers = dag.get("layers", [goals])
            conflicts = dag.get("conflicts", [])
            if conflicts:
                cycle_conflicts = [c for c in conflicts if c.get("type") == "cycle"]
                if cycle_conflicts:
                    return GoalResult(
                        status="failed",
                        reason=f"环形依赖: {cycle_conflicts}",
                    )
        else:
            layers = [goals]

        # P0-1: 逐层执行——Semaphore 包裹每个协程
        results: list[GoalResult] = []
        sem = asyncio.Semaphore(self._max_parallel)

        async def _run_one(g):
            async with sem:
                return await self.run(g)

        for layer in layers:
            layer_results = await asyncio.gather(*[_run_one(g) for g in layer])
            results.extend(layer_results)

        # 汇总报告
        total_tokens = sum(r.total_tokens for r in results)
        completed = sum(1 for r in results if r.status == "done")

        return GoalResult(
            status="done" if completed == len(results) else "partial",
            tasks_completed=completed,
            total_tokens=total_tokens,
            report_path=_generate_batch_report(results),
        )

    # ── 内部: 辅助 ────────────────────────────────────

    async def _clarify(self, goal: GoalSession) -> GoalSession:
        """需求澄清——Clarifier Agent 多轮对话。"""
        if not self.clarifier:
            return goal
        try:
            clarified = await self.clarifier.clarify(goal.description)
            goal.description = clarified.get("description", goal.description)
            goal.constraints = clarified.get("constraints", goal.constraints)
            goal.verification_commands = clarified.get(
                "verification_commands", goal.verification_commands
            )
            # 记录到 Ledger
            self.memory.goal_description = goal.description
            self.memory.constraints = goal.constraints
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("clarifier_failed", error=str(e))
        return goal

    async def _present_for_confirmation(self, estimate, spec, goal: GoalSession) -> bool:
        """展示拆解结果——等待用户确认。"""
        logger.info("present_for_confirmation", goal_id=goal.id, spec_title=spec.title)
        return True

    def _budget_exhausted(self, goal: GoalSession) -> bool:
        """检查预算是否耗尽。"""
        if goal.total_token_budget > 0 and goal.token_consumed >= goal.total_token_budget:
            logger.warning(
                "goal_budget_exhausted",
                budget=goal.total_token_budget,
                consumed=goal.token_consumed,
            )
            return True
        if goal.max_runtime_seconds > 0 and goal.started_at:
            try:
                started_str = goal.started_at.replace("Z", "+00:00")
                started_dt = datetime.fromisoformat(started_str)
                elapsed = time.time() - started_dt.timestamp()
            except (ValueError, TypeError):
                logger.warning("goal_time_parse_failed", started_at=goal.started_at)
                return False
            if elapsed >= goal.max_runtime_seconds:
                logger.warning(
                    "goal_time_exhausted", max=goal.max_runtime_seconds, elapsed=int(elapsed)
                )
                return True
        return False


