"""ComposeOrchestrator——spec-driven 多 Agent 编排引擎。

对标 MiMo Code compose:subagent 流程:
1. Read spec → extract tasks
2. Per task: dispatch implementer subagent via ActorSpawn
3. Two-stage review gate: spec review → code quality review
4. Finish: final review → merge
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from orbit.actors.spawn import ActorSpawn
    from orbit.worktree.manager import WorktreeManager

from orbit.compose.models import Spec, Task
from orbit.compose.parser import ComposeParser
from orbit.scheduler.orchestrator import Scheduler

logger = structlog.get_logger()


class ComposeOrchestrator:
    """Spec-driven 编排器。

    Usage:
        orchestrator = ComposeOrchestrator(actor_spawn, parser)
        result = await orchestrator.run_spec(spec_text)
    """

    def __init__(
        self,
        actor_spawn: ActorSpawn | None = None,
        parser: ComposeParser | None = None,
        scheduler: Scheduler | None = None,
        max_retries: int = 2,
        worktree_manager: WorktreeManager | None = None,  # Phase 4 AC-B4
    ) -> None:
        self.actor_spawn = actor_spawn
        self.parser = parser or ComposeParser()
        self.scheduler = scheduler
        self.MAX_RETRIES = max_retries
        self._worktree = worktree_manager

    async def run_spec(
        self,
        spec_text: str,
        parent_task_id: str = "",
        background: bool = False,
    ) -> dict[str, Any]:
        """执行 spec——完整的 spec-driven 开发流程。

        流程:
        1. 解析 spec → 提取 tasks
        2. spec review（方案审查门禁）
        3. 按依赖顺序执行 tasks（通过 ActorSpawn）
        4. code quality review（代码审查门禁）
        5. 汇总结果
        """
        # 1. 解析 spec
        try:
            spec = self.parser.parse_spec(spec_text)
        except (ValueError, KeyError) as e:
            return {"status": "error", "error": f"spec 解析失败: {str(e)}"}

        logger.info(
            "compose_run_spec",
            title=spec.title,
            task_count=len(spec.tasks),
        )

        # Phase 4 AC-B4: 创建 Worktree 隔离工作区
        wt_record = None
        if self._worktree:
            try:
                from orbit.worktree.models import WorktreeStrategy

                wt_record = await self._worktree.create(strategy=WorktreeStrategy.DELEGATE)
                logger.info(
                    "compose_worktree_created",
                    id=wt_record.worktree_id,
                    branch=wt_record.branch_name,
                )
            except Exception as e:
                logger.warning("compose_worktree_failed_fallback_off", error=str(e))

        # 2. Spec review（对标 MiMo spec review）
        spec_review = await self._spec_review(spec)
        if not spec_review.get("ok", True):
            return {
                "status": "error",
                "error": f"spec 审查未通过: {spec_review.get('reason', '')}",
                "spec_review": spec_review,
            }

        # 3. 按依赖顺序执行 tasks
        try:
            task_order = self._topological_sort(spec.tasks)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        results: dict[str, dict] = {}
        done: set[str] = set()

        for task in task_order:
            for dep_id in task.depends_on:
                if dep_id not in done:
                    logger.warning(
                        "task_dependency_not_ready",
                        task_id=task.id,
                        dependency=dep_id,
                    )

            logger.info("compose_dispatch_task", task_id=task.id, role=task.agent_role)

            try:
                if self.actor_spawn:
                    deferred = await self.actor_spawn.spawn(
                        task=task.description,
                        role=task.agent_role,
                        parent_task_id=parent_task_id,
                        background=background,
                        workspace_path=wt_record.path if wt_record else "",
                    )
                    if not background:
                        result = await deferred.result(timeout=600)
                        results[task.id] = result
                    else:
                        results[task.id] = {
                            "status": "dispatched",
                            "actor_id": deferred.actor_id,
                        }
                else:
                    results[task.id] = {
                        "status": "ok",
                        "output": f"[mock] {task.agent_role}: {task.description[:100]}",
                    }
            except (TimeoutError, RuntimeError, OSError, ValueError) as e:
                logger.error("task_failed", task_id=task.id, error=str(e), exc_info=True)
                results[task.id] = await self._retry_task(task, parent_task_id, error=str(e))

            done.add(task.id)

        # 4. Code quality review
        code_review = await self._code_review(spec, results)

        # 5. 汇总
        all_ok = all(r.get("status") in ("ok", "dispatched") for r in results.values())

        return {
            "status": "ok" if all_ok else "partial",
            "spec": spec.title,
            "tasks": results,
            "spec_review": spec_review,
            "code_review": code_review,
        }

    # ── 内部门禁 ──────────────────────────────────

    async def _spec_review(self, spec: Spec) -> dict[str, Any]:
        """方案审查门禁——检查 spec 完整性。"""
        issues = []

        if not spec.title:
            issues.append("缺少 title")
        if not spec.tasks:
            issues.append("tasks 列表为空")
        for task in spec.tasks:
            if not task.description:
                issues.append(f"任务 {task.id} 缺少 description")
            # P2-1: 自依赖检查
            if task.id in task.depends_on:
                issues.append(f"任务 {task.id} 依赖自身——不允许")
            if task.depends_on:
                known_ids = {t.id for t in spec.tasks}
                unknown = set(task.depends_on) - known_ids
                if unknown:
                    issues.append(f"任务 {task.id} 依赖未知任务: {unknown}")

        if issues:
            return {"ok": False, "reason": "; ".join(issues)}
        return {"ok": True, "reason": "spec 审查通过"}

    async def _code_review(self, spec: Spec, results: dict) -> dict[str, Any]:
        """代码审查门禁——P1-2: 增强检查产物+错误残留。"""
        failed = []
        warnings = []
        for task_id, result in results.items():
            status = result.get("status", "unknown")
            if status == "error":
                failed.append({"task_id": task_id, "error": result.get("error", "未知错误")})
                continue
            output = result.get("output", "")
            if not output or len(str(output)) < 10:
                warnings.append({"task_id": task_id, "warning": "输出过短，可能无实质产物"})
            if "Traceback" in str(output) or "Error:" in str(output):
                warnings.append({"task_id": task_id, "warning": "输出包含错误堆栈残留"})

        review: dict[str, Any] = {
            "ok": len(failed) == 0,
            "reason": f"全部 {len(results)} 个任务通过",
        }
        if failed:
            review["failed_tasks"] = failed
        if warnings:
            review["warnings"] = warnings
        return review

    # ── 拓扑排序 ──────────────────────────────────

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """Kahn 算法——O(V+E)。P1-1: deque 保证 O(1) 出队。"""
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: len(t.depends_on) for t in tasks}
        adj: dict[str, list[str]] = {t.id: [] for t in tasks}

        for t in tasks:
            for dep in t.depends_on:
                if dep in adj:
                    adj[dep].append(t.id)

        queue: deque[str] = deque(tid for tid, deg in in_degree.items() if deg == 0)
        result: list[Task] = []

        while queue:
            tid = queue.popleft()
            result.append(task_map[tid])
            for neighbor in adj.get(tid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # P1-4: 环形依赖→抛异常
        if len(result) != len(tasks):
            remaining = set(t.id for t in tasks) - {t.id for t in result}
            raise ValueError(f"环形依赖——以下任务形成循环: {remaining}")

        return result

    # ── 重试 ──────────────────────────────────────

    async def _retry_task(
        self,
        task: Task,
        parent_task_id: str,
        error: str,
    ) -> dict[str, Any]:
        """任务失败重试——最多 self.MAX_RETRIES 次。

        P1-3: 非 error 状态视为成功（ok/dispatched/partial 均非失败）。
        P2-2: 重试次数从实例配置 self.MAX_RETRIES 读取。
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            logger.info("task_retry", task_id=task.id, attempt=attempt)
            try:
                if self.actor_spawn:
                    deferred = await self.actor_spawn.spawn(
                        task=task.description,
                        role=task.agent_role,
                        parent_task_id=parent_task_id,
                    )
                    result = await deferred.result(timeout=600)
                    # P1-3: 非 error 即视为成功
                    if result.get("status") != "error":
                        return result
                else:
                    return {
                        "status": "ok",
                        "output": f"[mock retry {attempt}] 完成",
                    }
            except (TimeoutError, RuntimeError, OSError) as e:
                logger.warning(
                    "retry_failed",
                    task_id=task.id,
                    attempt=attempt,
                    error=str(e),
                    exc_info=True,
                )

        return {
            "status": "error",
            "error": f"重试 {self.MAX_RETRIES} 次后仍失败: {error}",
        }
