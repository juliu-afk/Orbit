"""AlignmentCheck——RefAct 对齐检查。

对标 SWE-Agent RefAct: "reflect before action, not after"。
每 5 个子任务完成后，meta-orchestrator 检查整体对齐。
不对齐 → 暂停等用户确认；连续 2 次不对齐 → 强制暂停。
"""

from __future__ import annotations

import json
import structlog
from typing import Any

logger = structlog.get_logger("orbit.goal")

ALIGNMENT_CHECK_PROMPT = """请反思当前执行轨迹与原始目标的对应关系:

1. 原始目标是什么？
2. 当前已完成哪些子任务？有哪些证据？
3. 当前轨迹是否仍对齐原始目标？
   - 对齐: 继续执行
   - 偏离: 哪个子任务开始偏离的？应该回退到哪个检查点？
4. 是否有范围蔓延（做了超出原始目标的事情）？

输出 JSON: {"aligned": true/false, "deviation_task": null|"task-id", "suggestion": ""}"""


class AlignmentResult:
    """对齐检查结果。"""

    def __init__(
        self,
        aligned: bool = True,
        deviation_task: str = "",
        suggestion: str = "",
        should_pause: bool = False,
        message: str = "",
    ) -> None:
        self.aligned = aligned
        self.deviation_task = deviation_task
        self.suggestion = suggestion
        self.should_pause = should_pause
        self.message = message


class AlignmentCheck:
    """RefAct 对齐检查。

    Usage:
        check = AlignmentCheck(llm_client)
        result = await check.check(goal, progress)
        if not result.aligned:
            # 暂停或回退
    """

    CHECK_INTERVAL = 5  # 每 5 个子任务检查一次

    def __init__(self, llm: Any = None) -> None:  # LLMClient
        self._llm = llm

    async def check(
        self,
        goal: Any,  # GoalSession
        progress: dict[str, str],
    ) -> AlignmentResult:
        """执行对齐检查。

        仅每 CHECK_INTERVAL 个子任务完成时触发。
        """
        completed = sum(1 for s in progress.values() if s == "done")
        if completed == 0 or completed % self.CHECK_INTERVAL != 0:
            return AlignmentResult(aligned=True)

        if not self._llm:
            return AlignmentResult(aligned=True, message="mock mode——默认对齐")

        progress_text = "\n".join(f"- [{s}] {tid}" for tid, s in progress.items())
        prompt = (
            f"原始目标: {getattr(goal, 'description', str(goal))}\n"
            f"约束: {getattr(goal, 'constraints', [])}\n"
            f"当前进度:\n{progress_text}\n\n"
            f"{ALIGNMENT_CHECK_PROMPT}"
        )

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt="你是目标对齐检查员——判断执行轨迹是否偏离原始目标。",
                temperature=0.0,
                max_tokens=300,
            )
            response = await self._llm.generate(req, task_id="alignment")
            data = json.loads(response.content or "{}")

            aligned = data.get("aligned", True)
            should_pause = False

            if not aligned:
                logger.warning(
                    "goal_alignment_drift",
                    deviation=data.get("deviation_task"),
                    suggestion=data.get("suggestion"),
                )
                # 连续 2 次不对齐 → 暂停
                goal.consecutive_misalignments = getattr(goal, "consecutive_misalignments", 0) + 1
                if goal.consecutive_misalignments >= 2:
                    should_pause = True
            else:
                goal.consecutive_misalignments = 0

            return AlignmentResult(
                aligned=aligned,
                deviation_task=data.get("deviation_task", ""),
                suggestion=data.get("suggestion", ""),
                should_pause=should_pause,
                message="连续 2 次不对齐——建议暂停" if should_pause else "",
            )
        except Exception as e:
            logger.warning("alignment_check_failed_fail_open", error=str(e))
            return AlignmentResult(aligned=True)
