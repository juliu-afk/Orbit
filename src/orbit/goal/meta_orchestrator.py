"""MetaOrchestrator——Goal 级编排器。

v5 架构核心:
- Intake Router 智能判定输入形态
- DependencyAnalyzer 分析复数任务依赖
- 每个子任务独立 SubTaskSession（独立 128K 上下文）
- 子任务间通过 git merge commit 传递状态 —— 0 Token 开销
- 自主 PR 合入门禁: CritiqueAgent APPROVED + ExecutorVerifier 通过 + RegressionGuard 无回归
"""

from __future__ import annotations

import asyncio
import structlog
import time
from datetime import UTC, datetime

from orbit.goal.intake_router import IntakeRouter
from orbit.goal.memory_tiers import ThreeTierMemory
from typing import TYPE_CHECKING, Any

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
        clarifier: Any = None,          # ClarifierAgent
        progress_tracker: ProgressTracker | None = None,
        alignment_check: AlignmentCheck | None = None,
        regression_guard: RegressionGuard | None = None,
        memory: ThreeTierMemory | None = None,
        preflight: PreFlightEstimator | None = None,
        budget_allocator: BudgetAllocator | None = None,
        verifier: ExecutorVerifier | None = None,
        critique_agent: CritiqueAgent | None = None,
<<<<<<< HEAD
=======
        compose_orchestrator: Any = None,  # ComposeOrchestrator
        ensemble: Any = None,  # ModelEnsemble
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
        worktree_manager: WorktreeManager | None = None,
        agent_factory: Any = None,       # AgentFactory
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
<<<<<<< HEAD
=======
        self.compose_orchestrator = compose_orchestrator
        self.ensemble = ensemble
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
        self._worktree = worktree_manager
        self._agent_factory = agent_factory
        self._max_parallel = max_parallel_tasks

    # ── 公共 API ──────────────────────────────────────

    async def run(self, goal: GoalSession) -> GoalResult:
        """执行完整 Goal 生命周期。"""
        started_at = time.time()
        goal.started_at = datetime.now(UTC).isoformat()

        try:
            # 阶段0: Intake Router
            decision = await self.intake_router.route(goal)

            # 复数文档→依赖分析+DAG调度
            if decision.is_batch:
                return await self._run_batch(goal)

            # 按需澄清
            if decision.needs_clarify and self.clarifier:
                goal = await self._clarify(goal)

            # 按需拆解
            if decision.needs_decompose and self.compose_bridge:
                if not goal.spec:
                    estimate = None
                    if self.preflight:
                        estimate = await self.preflight.estimate(goal.description)
                    spec = await self.compose_bridge.generate_spec(goal)
                    confirmed = await self._present_for_confirmation(estimate, spec, goal)
                    if not confirmed:
                        return GoalResult(status="cancelled", reason="用户取消")
                    goal.spec = spec.model_dump() if hasattr(spec, 'model_dump') else spec
                    goal.sub_tasks = {t.id: "pending" for t in spec.tasks}

            # 已有 TaskDAG→直接执行
            spec_data = goal.spec
            if not spec_data:
                # 无 spec 且无 compose_bridge——单任务模式
                return await self._run_single_task(goal)

            spec = self._deserialize_spec(spec_data)
<<<<<<< HEAD
=======

            # Goal→Compose: delegate to ComposeOrchestrator when available
            if self.compose_orchestrator:
                logger.info("goal_delegating_to_compose", goal_id=goal.id)
                compose_result = await self.compose_orchestrator.run_spec(goal.description, parent_task_id=goal.id)
                elapsed = time.time() - started_at
                ok = compose_result.get("status") == "ok"
                return GoalResult(status="done" if ok else "partial", total_time_seconds=elapsed)

>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
            layers = self._topological_layers(spec.tasks)
            previous_merge_shas: dict[str, str] = {}

            # 阶段1: 分层调度
            completed_count = 0
            for layer_idx, layer in enumerate(layers):
                # 解析 base_ref
                task_bases = self._resolve_bases(layer, previous_merge_shas)

                # 分配预算
                budgets = {}
                if self.budget_allocator:
                    budgets = self.budget_allocator.allocate(
                        layer, goal.total_token_budget - goal.token_consumed
                    )

                # 层内并行
                layer_results = await asyncio.gather(*[
                    self._run_subtask(t, task_bases.get(t.id, "main"), goal, budgets.get(t.id, 0))
                    for t in layer
                ])

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
                        return GoalResult(
                            status="paused",
                            reason=f"Task {task.id} 批判退回超过上限",
                        )
                    else:
                        goal.consecutive_failures += 1
                        if goal.consecutive_failures >= 3:
                            return GoalResult(
                                status="failed",
                                reason=f"连续 {goal.consecutive_failures} 个子任务失败",
                            )

                # 进度更新
                if self.progress_tracker:
                    await self.progress_tracker.update(goal)

                # 对齐检查（每 5 Task）
                if completed_count % 5 == 0 and self.alignment_check:
                    align = await self.alignment_check.check(goal, goal.sub_tasks)
                    if not align.aligned:
                        goal.consecutive_misalignments += 1
                        if goal.consecutive_misalignments >= 2:
                            return GoalResult(status="paused", reason="连续 2 次对齐失败")
                    else:
                        goal.consecutive_misalignments = 0

                # 预算检查
                if self._budget_exhausted(goal):
                    return GoalResult(
                        status="done", reason="预算耗尽",
                        tasks_completed=completed_count,
                    )

            # 汇总
            elapsed = time.time() - started_at
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
            return GoalResult(
                status="failed",
                reason=str(e),
                total_time_seconds=time.time() - started_at,
            )

    # ── 内部: 子任务调度 ───────────────────────────────

    async def _run_subtask(
        self,
        task: Any,  # Task
        base_ref: str,
        goal: GoalSession,
        budget: int,
    ) -> SubTaskResult:
        """调度单个 SubTaskSession。"""
        from orbit.goal.subtask_session import SubTaskSession

        session = SubTaskSession(
            task=task,
            base_ref=base_ref,
            goal_context=self.memory.to_task_context(),
            goal=goal,
            agent_factory=self._agent_factory,
            worktree_manager=self._worktree,
            budget_tracker=None,  # 子任务独立 tracker——TODO
            critique_agent=self.critique_agent,
            verifier=self.verifier,
        )
        return await session.run_full_pipeline()

    async def _run_single_task(self, goal: GoalSession) -> GoalResult:
        """单任务模式——无拆解，直接执行。"""
        # 创建虚拟 Task
        from orbit.compose.models import Task as ComposeTask
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
        goals = [self._parse_to_goal(doc) for doc in batch_goals]

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
<<<<<<< HEAD
        for layer in layers:
            async def _run_one(g):
                async with sem:
                    return await self.run(g)
=======

        async def _run_one(g):
            async with sem:
                return await self.run(g)

        for layer in layers:
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
            layer_results = await asyncio.gather(*[_run_one(g) for g in layer])
            results.extend(layer_results)

        # 汇总报告
        total_tokens = sum(r.total_tokens for r in results)
        completed = sum(1 for r in results if r.status == "done")

        return GoalResult(
            status="done" if completed == len(results) else "partial",
            tasks_completed=completed,
            total_tokens=total_tokens,
            report_path=self._generate_batch_report(results),
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
<<<<<<< HEAD
        except asyncio.CancelledError:
            raise
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
        except Exception as e:
            logger.warning("clarifier_failed", error=str(e))
        return goal

    async def _present_for_confirmation(
        self, estimate, spec, goal: GoalSession
    ) -> bool:
        """展示拆解结果——等待用户确认。

        实际实现: 通过 WebSocket/chat 界面展示。
        此处为占位——返回 True 表示自动确认。
        """
        # TODO: 接入 chat 交互层——展示 Spec + 预算 + 等待用户 Y/n
        logger.info("present_for_confirmation", goal_id=goal.id, spec_title=spec.title)
        return True

    def _budget_exhausted(self, goal: GoalSession) -> bool:
        """检查预算是否耗尽。"""
        if goal.total_token_budget > 0 and goal.token_consumed >= goal.total_token_budget:
            logger.warning("goal_budget_exhausted", budget=goal.total_token_budget, consumed=goal.token_consumed)
            return True
        if goal.max_runtime_seconds > 0 and goal.started_at:
<<<<<<< HEAD
            # P1-NEW5: 更稳健的 ISO 解析
            try:
                started_str = goal.started_at.replace("Z", "+00:00")
                started_dt = datetime.fromisoformat(started_str)
                elapsed = time.time() - started_dt.timestamp()
            except (ValueError, TypeError):
                logger.warning("goal_time_parse_failed", started_at=goal.started_at)
=======
            # P1-3: 防御 None/空字符串
            try:
                started_str = goal.started_at.replace("Z", "+00:00")
                elapsed = time.time() - datetime.fromisoformat(started_str).timestamp()
            except (ValueError, TypeError, AttributeError):
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
                return False
            if elapsed >= goal.max_runtime_seconds:
                logger.warning("goal_time_exhausted", max=goal.max_runtime_seconds, elapsed=int(elapsed))
                return True
        return False

    def _generate_batch_report(self, results: list[GoalResult]) -> str:
        """生成批量执行报告——markdown 文件路径。"""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
        path = f"docs/goal-report-{timestamp}.md"
        # TODO: 写入文件
        logger.info("batch_report_generated", path=path, count=len(results))
        return path

    @staticmethod
    def _resolve_bases(
        layer: list[Any],  # list[Task]
        previous_merges: dict[str, str],
    ) -> dict[str, str]:
        """P1-1: 确定每个 task 的 base_ref。多依赖取最晚合入 SHA。"""
        bases = {}
        for t in layer:
            if not t.depends_on:
                bases[t.id] = "main"
            else:
                dep_shas = [previous_merges[d] for d in t.depends_on if d in previous_merges]
                if not dep_shas:
                    logger.warning("resolve_bases_no_deps_found", task_id=t.id, depends_on=list(t.depends_on))
                    bases[t.id] = "main"
                else:
                    bases[t.id] = dep_shas[-1]
        return bases

    @staticmethod
    def _topological_layers(tasks: list[Any]) -> list[list[Any]]:
        """P1-2/P2-6: Kahn 算法按层分组。缺失依赖 warning，不可达节点报错。"""
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: len(t.depends_on) for t in tasks}
        adj: dict[str, list[str]] = {t.id: [] for t in tasks}
        for t in tasks:
            for dep in t.depends_on:
                if dep in adj:
                    adj[dep].append(t.id)
                else:
                    logger.warning("topological_sort_missing_dependency", task_id=t.id, missing_dep=dep)

        layers = []
        current = [t for t in tasks if in_degree[t.id] == 0]
        while current:
            layers.append(current)
            nxt = []
            for t in current:
                for neighbor in adj.get(t.id, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        nxt.append(task_map[neighbor])
            current = nxt

        if sum(len(l) for l in layers) != len(tasks):
            remaining = {t.id for t in tasks} - {t.id for l in layers for t in l}
            raise ValueError(f"环形依赖或不可达节点: {remaining}")
        return layers

    @staticmethod
    def _deserialize_spec(spec_data: dict) -> Any:
<<<<<<< HEAD
        """反序列化 Spec——兼容 dict 和 pydantic。"""
        try:
            from orbit.compose.models import Spec, Task
            return Spec(**spec_data)
        except Exception:
=======
        """反序列化 Spec——兼容 dict 和 pydantic。P1-4: 日志记录。"""
        try:
            from orbit.compose.models import Spec, Task
            return Spec(**spec_data)
        except Exception as e:
            logger.warning("spec_deserialize_failed", error=str(e)[:200])
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
            return spec_data

    @staticmethod
    def _parse_to_goal(doc: dict) -> GoalSession:
        """批量文档转 GoalSession。"""
        return GoalSession(
            description=doc.get("description", ""),
            constraints=doc.get("constraints", []),
            verification_commands=doc.get("verification_commands", []),
        )
