"""GoalJudge——两级门禁判定模型。

对标 MiMo Code session/goal.ts + session/prompt.ts:2050-2160.

流程:
1. Task Gate（便宜）——检查是否有未完成的子Actor
2. Goal Gate（expensive）——编译 transcript → LLM judge

WHY fail-open: judge 出错时当作已完成——不困住用户。
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.goal_judge.models import JUDGE_SYSTEM_PROMPT, Goal, Verdict

logger = structlog.get_logger()


class GoalJudge:
    """目标达成判定器。

    Usage:
        judge = GoalJudge(llm_client, actor_registry)
        verdict = await judge.evaluate(goal, transcript)
        if verdict.ok:
            # 允许 Agent 停止
    """

    def __init__(self, llm: Any = None, registry: Any = None) -> None:
        self.llm = llm  # LLMClient
        self.registry = registry  # ActorRegistry

    async def evaluate(
        self,
        goal: Goal,
        transcript: str = "",
        task_id: str = "",
    ) -> Verdict:
        """两级门禁判定。

        Args:
            goal: 用户目标
            transcript: Agent 会话 transcript
            task_id: 父任务 ID

        Returns:
            Verdict——ok=true 表示可以停止
        """
        # 1. Task Gate（便宜预检——检查未完成的子Actor）
        task_verdict = await self._task_gate(task_id)
        if task_verdict is not None:
            return task_verdict

        # 2. 无活跃 goal → 跳过 goal gate
        if not goal.description:
            return Verdict(ok=True, impossible=False, reason="no_active_goal")

        # 3. 检查硬上限
        if goal.react_count >= goal.MAX_REACT:
            logger.warning(
                "max_goal_react_exceeded",
                react_count=goal.react_count,
                max_react=goal.MAX_REACT,
            )
            return Verdict(
                ok=True,
                impossible=False,
                reason=f"MAX_GOAL_REACT ({goal.MAX_REACT}) 已达硬上限——强制完成",
            )

        # 4. Goal Gate——LLM judge
        goal.react_count += 1

        if self.llm is None:
            # mock 模式——无 LLM → fail-open: 当作完成
            logger.info("goal_judge_mock_mode_fail_open")
            return Verdict(ok=True, impossible=False, reason="mock mode fail-open")

        try:
            return await self._goal_gate(goal, transcript)
        except Exception as e:
            # fail-open: judge 失败 → 当作已完成
            logger.error("goal_judge_failed_fail_open", error=str(e))
            return Verdict(ok=True, impossible=False, reason=f"judge 失败→fail-open: {str(e)}")

    # ── 内部 ─────────────────────────────────────

    async def _task_gate(self, task_id: str) -> Verdict | None:
        """Task Gate: 检查是否有未完成的子Actor。

        Returns:
            None = 通过 task gate（无未完成任务），继续 goal gate
            Verdict = 存在未完成任务——阻止停止
        """
        if self.registry is None:
            return None

        try:
            active = self.registry.get_by_parent(task_id)
            pending_or_running = [
                a for a in active
                if a.status.value in ("pending", "running")
            ]
            if pending_or_running:
                return Verdict(
                    ok=False,
                    impossible=False,
                    reason=f"存在 {len(pending_or_running)} 个未完成的子任务",
                )
        except Exception as e:
            logger.warning("task_gate_error", error=str(e))
            # task gate 失败 → 继续 goal gate（不阻塞）
        return None

    async def _goal_gate(self, goal: Goal, transcript: str) -> Verdict:
        """Goal Gate: LLM judge 判定。

        temperature=0 —— 确定性评估。
        """
        from orbit.gateway.schemas import LLMRequest

        # 截断 transcript——只送最近 8000 字符给 judge
        truncated = transcript[-8000:] if len(transcript) > 8000 else transcript

        prompt = (
            f"## 目标\n{goal.description}\n\n"
            f"## Agent 执行记录\n{truncated}\n\n"
            "请判定目标是否已完成。返回 JSON:"
        )

        req = LLMRequest(
            prompt=prompt,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=256,
            tools=None,
            tool_choice="auto",
            messages=None,
            provider=None,
        )

        response = await self.llm.generate(req, task_id="goal_judge")

        # 解析 JSON 响应
        import json

        try:
            content = response.content.strip()
            # 去除可能的 markdown code block
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            return Verdict(
                ok=data.get("ok", True),
                impossible=data.get("impossible", False),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            # JSON 解析失败 → fail-open
            logger.warning("verdict_parse_failed", content=response.content[:200])
            return Verdict(ok=True, impossible=False, reason=f"verdict 解析失败→fail-open: {str(e)}")
