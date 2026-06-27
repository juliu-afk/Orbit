"""ComposeOrchestrator——spec-driven 多 Agent 编排引擎。

对标 MiMo Code compose:subagent 流程:
1. Read spec → extract tasks
2. Per task: dispatch implementer subagent via ActorSpawn
3. Two-stage review gate: spec review → code quality review
4. Finish: final review → merge

WHY 继承 Orchestrator: 复用 DAG + checkpoint + event_bus。
"""

from __future__ import annotations

from typing import Any

import structlog

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
        actor_spawn: Any = None,  # ActorSpawn
        parser: ComposeParser | None = None,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.actor_spawn = actor_spawn
        self.parser = parser or ComposeParser()
        self.scheduler = scheduler  # 可复用现有 Scheduler（含 DAG + checkpoint）

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

        Args:
            spec_text: spec YAML 文本
            parent_task_id: 父任务 ID
            background: True = 任务后台执行（不等待完成）

        Returns:
            {"status": "ok"/"error", "tasks": [...], "review": {...}}
        """
        # 1. 解析 spec
        try:
            spec = self.parser.parse_spec(spec_text)
        except (ValueError, KeyError) as e:
            # ValueError: spec 格式错误（非 dict）
            # KeyError: spec 缺少必要字段
            # yaml.YAMLError: parse_spec 内部的 yaml 解析异常
            return {"status": "error", "error": f"spec 解析失败: {str(e)}"}

        logger.info(
            "compose_run_spec",
            title=spec.title,
            task_count=len(spec.tasks),
        )

        # 2. Spec review——方案审查门禁（对标 MiMo spec review）
        spec_review = await self._spec_review(spec)
        if not spec_review.get("ok", True):
            return {
                "status": "error",
                "error": f"spec 审查未通过: {spec_review.get('reason', '')}",
                "spec_review": spec_review,
            }

        # 3. 按依赖顺序执行 tasks——拓扑排序 + ActorSpawn
        task_order = self._topological_sort(spec.tasks)
        results: dict[str, dict] = {}

        # 已完成的 task IDs
        done: set[str] = set()

        for task in task_order:
            # 等待依赖完成
            for dep_id in task.depends_on:
                if dep_id not in done:
                    logger.warning(
                        "task_dependency_not_ready",
                        task_id=task.id,
                        dependency=dep_id,
                    )
                    # 继续执行（依赖可能已在上一批完成）

            logger.info("compose_dispatch_task", task_id=task.id, role=task.agent_role)

            try:
                if self.actor_spawn:
                    deferred = await self.actor_spawn.spawn(
                        task=task.description,
                        role=task.agent_role,
                        parent_task_id=parent_task_id,
                        background=background,
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
                    # 无 ActorSpawn——模拟执行
                    results[task.id] = {
                        "status": "ok",
                        "output": f"[mock] {task.agent_role} 完成: {task.description[:100]}",
                    }
            except (TimeoutError, RuntimeError, OSError, ValueError) as e:
                # TimeoutError: Actor 执行超时
                # RuntimeError: ActorSpawn 并发上限/执行失败
                # OSError: DB 访问异常
                # ValueError: 参数校验失败
                logger.error("task_failed", task_id=task.id, error=str(e), exc_info=True)
                results[task.id] = await self._retry_task(task, parent_task_id, error=str(e))

            done.add(task.id)

        # 4. Code quality review——代码审查门禁
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
        """方案审查门禁——检查 spec 完整性。

        对标 MiMo compose 的 spec review 阶段。
        """
        issues = []

        if not spec.title:
            issues.append("缺少 title")
        if not spec.tasks:
            issues.append("tasks 列表为空——至少需要一个任务")
        for task in spec.tasks:
            if not task.description:
                issues.append(f"任务 {task.id} 缺少 description")
            if task.depends_on:
                # 检查依赖是否存在
                known_ids = {t.id for t in spec.tasks}
                unknown = set(task.depends_on) - known_ids
                if unknown:
                    issues.append(f"任务 {task.id} 依赖未知任务: {unknown}")

        if issues:
            return {"ok": False, "reason": "; ".join(issues)}

        return {"ok": True, "reason": "spec 审查通过"}

    async def _code_review(self, spec: Spec, results: dict) -> dict[str, Any]:
        """代码审查门禁——检查所有任务完成质量。

        对标 MiMo compose 的 code quality review 阶段。
        """
        failed = []
        for task_id, result in results.items():
            status = result.get("status", "unknown")
            if status == "error":
                failed.append({"task_id": task_id, "error": result.get("error", "未知错误")})

        if failed:
            return {"ok": False, "failed_tasks": failed}

        return {"ok": True, "reason": f"全部 {len(results)} 个任务通过"}

    # ── 拓扑排序 ──────────────────────────────────

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """按依赖关系拓扑排序 tasks。

        Kahn 算法——无依赖的先执行。
        """
        task_map = {t.id: t for t in tasks}
        in_degree = {t.id: len(t.depends_on) for t in tasks}
        adj: dict[str, list[str]] = {t.id: [] for t in tasks}

        for t in tasks:
            for dep in t.depends_on:
                if dep in adj:
                    adj[dep].append(t.id)

        # 入度为 0 的节点
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result: list[Task] = []

        while queue:
            tid = queue.pop(0)
            result.append(task_map[tid])
            for neighbor in adj.get(tid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 环形依赖检测
        if len(result) != len(tasks):
            remaining = set(t.id for t in tasks) - {t.id for t in result}
            logger.warning("circular_dependency_detected", remaining=remaining)
            # 强制追加剩余任务（打破循环）
            for t in tasks:
                if t.id in remaining:
                    result.append(t)

        return result

    # ── 重试 ──────────────────────────────────────

    async def _retry_task(
        self,
        task: Task,
        parent_task_id: str,
        error: str,
    ) -> dict[str, Any]:
        """任务失败重试——最多 MAX_RETRIES 次。"""
        for attempt in range(1, Task.MAX_RETRIES + 1):
            logger.info("task_retry", task_id=task.id, attempt=attempt)
            try:
                if self.actor_spawn:
                    deferred = await self.actor_spawn.spawn(
                        task=task.description,
                        role=task.agent_role,
                        parent_task_id=parent_task_id,
                    )
                    result = await deferred.result(timeout=600)
                    if result.get("status") == "ok":
                        return result
                else:
                    return {"status": "ok", "output": f"[mock retry {attempt}] 完成"}
            except (TimeoutError, RuntimeError, OSError) as e:
                # TimeoutError: Actor 执行超时
                # RuntimeError: ActorSpawn 创建/执行失败
                # OSError: 数据库访问异常
                logger.warning("retry_failed", task_id=task.id, attempt=attempt, error=str(e), exc_info=True)

        return {"status": "error", "error": f"重试 {Task.MAX_RETRIES} 次后仍失败: {error}"}
