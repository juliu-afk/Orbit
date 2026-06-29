"""ProgressTracker——跨 Session 子任务进度跟踪。

维护结构化进度 JSON——独立于消息历史。
Agent 消息可能被压缩/丢弃，但进度状态持久化在 DB 中。

WHY 独立于消息历史: 消息历史被压缩后丢失结构化信息，
ProgressTracker 从 Beads 层恢复进度——Beads 不会被压缩。
"""

from __future__ import annotations

import structlog
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.goal.models import GoalSession

logger = structlog.get_logger("orbit.goal")


class ProgressTracker:
    """目标进度跟踪器——跨轮次维护子任务完成状态。

    Usage:
        tracker = ProgressTracker()
        goal = await tracker.update(goal, compose_results, verification)
    """

    async def update(
        self,
        goal: GoalSession,
        compose_results: dict | None = None,
        verification_results: list[dict] | None = None,
    ) -> GoalSession:
        """更新子任务进度。

        自动判定规则:
        - Compose result status=="ok" + 验证 passed → done
        - Compose result status=="ok" + 验证 not passed → in_progress
        - Compose result status=="error" → failed or retry
        """
        if compose_results:
            for task_id, result in compose_results.get("tasks", {}).items():
                current = goal.sub_tasks.get(task_id, "pending")
                new_status = self._determine_status(task_id, result, verification_results or [])
                # 只推进不倒退——done 保持 done
                if current != "done":
                    goal.sub_tasks[task_id] = new_status

        goal.updated_at = datetime.now(UTC).isoformat()
        return goal

    def build_progress_prompt(self, goal: GoalSession) -> str:
        """构建进度摘要——注入 Agent context。

        输出格式:
        ## 任务进度
        | 状态 | 任务ID |
        |------|--------|
        | ✅ done | task-1 |
        | 🔄 in_progress | task-2 |
        | ⏳ pending | task-3 |
        | ❌ failed | task-4 |
        """
        lines = ["## 任务进度", "| 状态 | 任务ID |", "|------|--------|"]
        icons = {"done": "✅", "in_progress": "🔄", "pending": "⏳", "failed": "❌", "retry": "🔁"}
        for task_id, status in goal.sub_tasks.items():
            icon = icons.get(status, "❓")
            lines.append(f"| {icon} {status} | {task_id} |")
        return "\n".join(lines)

    def build_checklist(self, goal: GoalSession) -> list[str]:
        """从 Spec 生成检查清单——逐项勾对。"""
        checklist = []
        for task_id, status in goal.sub_tasks.items():
            done = "x" if status == "done" else " "
            checklist.append(f"- [{done}] {task_id}")
        return checklist

    @staticmethod
    def _determine_status(
        task_id: str,
        result: dict,
        verification_results: list[dict],
    ) -> str:
        """判定单个子任务的新状态。"""
        status = result.get("status", "pending")
        if status == "ok":
            # 验证是否通过
            if verification_results:
                all_passed = all(r.get("passed", False) for r in verification_results)
                return "done" if all_passed else "in_progress"
            return "done"
        elif status == "error":
            return "failed"
        elif status == "critique_loop":
            return "retry"
        return "in_progress"
