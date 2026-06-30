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
        judge = GoalJudge(llm_client, actor_registry, memory_store)
        verdict = await judge.evaluate(goal, transcript)
        if verdict.ok:
            # 允许 Agent 停止

    Phase 1 CRAG: not_ok 时自动从 memory 检索相似经验，
    注入 verdict.suggestions——Agent 获得补充上下文。
    """

    def __init__(self, llm: Any = None, registry: Any = None, memory_store: Any = None) -> None:
        self.llm = llm  # LLMClient
        self.registry = registry  # ActorRegistry
        self._memory = memory_store  # MemoryStore (Phase 1 CRAG)

    async def evaluate(
        self,
        goal: Goal,
        transcript: str = "",
        task_id: str = "",
    ) -> Verdict:
        """两级门禁判定 + CRAG 补充检索。

        Args:
            goal: 用户目标
            transcript: Agent 会话 transcript
            task_id: 父任务 ID

        Returns:
            Verdict——ok=true 表示可以停止；
            not_ok 时 suggestions 包含 memory 检索的相似经验。
        """
        # 1. Task Gate（便宜预检——检查未完成的子Actor）
        task_verdict = await self._task_gate(task_id)
        if task_verdict is not None:
            return self._enrich_with_suggestions(task_verdict, transcript)

        # 2. 无活跃 goal → 跳过 goal gate
        if not goal.description:
            return Verdict(ok=True, reason="no_active_goal")

        # 3. 检查硬上限
        if goal.react_count >= goal.MAX_REACT:
            logger.warning(
                "max_goal_react_exceeded",
                react_count=goal.react_count,
                max_react=goal.MAX_REACT,
            )
            return Verdict(
                ok=True,
                reason=f"MAX_GOAL_REACT ({goal.MAX_REACT}) 已达硬上限——强制完成",
            )

        # 4. Goal Gate——LLM judge
        goal.react_count += 1

        if self.llm is None:
            logger.info("goal_judge_mock_mode_fail_open")
            return Verdict(ok=True, reason="mock mode fail-open")

        try:
            verdict = await self._goal_gate(goal, transcript)
            return self._enrich_with_suggestions(verdict, transcript)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            logger.error("goal_judge_failed_fail_open", error=str(e), exc_info=True)
            return Verdict(ok=True, reason=f"judge 失败→fail-open: {str(e)}")

    def _enrich_with_suggestions(self, verdict: Verdict, transcript: str) -> Verdict:
        """CRAG: not_ok 时从 memory 检索相似经验注入 suggestions。

        WHY 不内嵌在 evaluate: 独立方法方便测试和禁用 CRAG。
        """
        if verdict.ok or not self._memory:
            return verdict
        try:
            from orbit.memory.models import MemorySearchQuery

            # 用 transcript 关键片段搜索——取最后 500 字符
            query_text = transcript[-500:] if len(transcript) > 500 else transcript
            results = self._memory.search(MemorySearchQuery(query=query_text, max_results=3))
            if results:
                verdict.suggestions = [r.snippet for r in results]
                logger.info("crag_suggestions_found", count=len(results))
        except (OSError, RuntimeError, ValueError) as e:
            # CRAG 失败不阻塞——静默降级
            logger.debug("crag_search_failed", error=str(e))
        return verdict

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
            pending_or_running = [a for a in active if a.status.value in ("pending", "running")]
            if pending_or_running:
                return Verdict(
                    ok=False,
                    reason=f"存在 {len(pending_or_running)} 个未完成的子任务",
                )
        except (OSError, RuntimeError, ValueError, KeyError) as e:
            # OSError: SQLite I/O 错误
            # RuntimeError: registry 查询异常
            # ValueError/KeyError: 数据格式异常
            logger.warning("task_gate_error", error=str(e), exc_info=True)
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
            temperature=0.0,  # 确定性评估
            max_tokens=256,  # Verdict 只需 ~100 tokens
        )

        response = await self.llm.generate(req, task_id="goal_judge")

        # 解析 JSON 响应
        import json
        import re

        try:
            content = response.content.strip()
            # P0-6 (Issue#126): Markdown 剥离缺陷修复——
            # 原逻辑仅处理以 ``` 开头的情况，可被 "```json\n{...}\n```" 之外的格式绕过
            # 用正则提取 JSON 块：匹配 ```json ... ``` 或无包裹的纯 JSON
            _md_json = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if _md_json:
                content = _md_json.group(1)
            else:
                # 无 markdown 包裹时提取第一个 JSON 对象
                _json_start = content.find("{")
                if _json_start >= 0:
                    content = content[_json_start:]
                    _json_end = content.rfind("}") + 1
                    if _json_end > 0:
                        content = content[:_json_end]
            data = json.loads(content)
            return Verdict(
                ok=data.get("ok", True),  # 默认 fail-open
                impossible=data.get("impossible", False),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            # JSON 解析失败 → fail-open（不阻塞 Goal 流程）
            logger.warning("verdict_parse_failed", content=response.content[:200])
            return Verdict(ok=True, reason=f"verdict 解析失败→fail-open: {str(e)}")
