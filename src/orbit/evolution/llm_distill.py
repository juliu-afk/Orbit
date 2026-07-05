"""EvolveR LLM 语义蒸馏 (Phase E1).

WHY 区别于 DistillationEngine (Phase C):
  DistillationEngine 做规则蒸馏——轨迹→失败/成功模式→简单字符串原则。
  LLMDistiller 做语义蒸馏——将多条同类轨迹喂给 LLM → "这些成功轨迹有什么共同模式？"
  提炼出更高质量、更抽象的跨任务策略原则。

对标: EvolveR 第②阶段——离线自蒸馏
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient
    from orbit.evolution.anchor import AnchorGuard
    from orbit.evolution.distill import DistillationEngine, StrategyPrinciple

import structlog

logger = structlog.get_logger("orbit.evolution.llm_distill")

# LLM 蒸馏 Prompt——从多条同类轨迹中提炼共同模式
DISTILL_PROMPT = """You are analyzing {count} successful task trajectories from the "{category}" domain to extract reusable strategy principles.

### Trajectories Summary
{summaries}

### Instructions
1. Identify 1-3 common patterns across these trajectories
2. For each pattern, write it as a reusable principle: "When [situation], [strategy]. Because [why]."
3. Format each principle as a single sentence
4. Only output JSON array of strings

Example: "When analyzing year-end revenue, check delivery notes 5 days before and after December 31. Because cutoff errors cluster around period boundaries."

Output JSON array:
["principle 1", "principle 2", "principle 3"]"""


class LLMDistiller:
    """LLM 语义蒸馏器——批量轨迹→高质量原则。

    用法:
        distiller = LLMDistiller(llm=llm, anchor=guard, engine=de)
        principles = await distiller.distill_batch(trajectories, category="审计")
        # principles 自动存入 DistillationEngine + 经 ANCHOR 审查
    """

    MAX_TRAJ_PER_BATCH = 10

    def __init__(
        self,
        llm: LLMClient | None = None,
        anchor: AnchorGuard | None = None,
        engine: DistillationEngine | None = None,
    ) -> None:
        self._llm = llm
        self._anchor = anchor
        self._engine = engine

    async def distill_batch(
        self, trajectories: list[dict], category: str = "",
    ) -> list[StrategyPrinciple]:
        """从多条同类轨迹中 LLM 语义蒸馏策略原则。

        流程:
          1. 轨迹摘要——每条约 200 字
          2. LLM prompt → JSON 字符串数组
          3. 每条经 ANCHOR 审查
          4. 通过审查的存入 DistillationEngine
        """
        if len(trajectories) < 3:
            logger.debug("llm_distill_too_few", count=len(trajectories))
            return []

        if self._llm is None:
            logger.debug("llm_distill_no_llm")
            return []

        # 1. 构建轨迹摘要
        summaries = self._build_summaries(trajectories[: self.MAX_TRAJ_PER_BATCH])

        # 2. LLM 蒸馏
        prompt = DISTILL_PROMPT.format(
            count=len(trajectories), category=category or "通用", summaries=summaries,
        )
        try:
            from orbit.gateway.schemas import LLMRequest
            req = LLMRequest(
                prompt=prompt,
                system_prompt="You are a strategy extraction system. Output JSON array only.",
                task_type="structured_output",
            )
            result = await self._llm.generate(req, task_id="llm_distill")
            principles_raw = json.loads(result.content.strip())
            if not isinstance(principles_raw, list):
                principles_raw = [str(principles_raw)]
        except Exception as e:
            logger.warning("llm_distill_failed", error=str(e))
            return []

        # 3. ANCHOR 审查 + 存入引擎
        principles: list[StrategyPrinciple] = []
        for text in principles_raw:
            text = str(text).strip()
            if not text or len(text) < 10:
                continue

            # ANCHOR 检查
            if self._anchor:
                verdict = self._anchor.check_after_distill(text)
                if verdict.verdict.value == "rejected":
                    logger.info("anchor_rejected_principle", text=text[:100])
                    continue

            # 存入 DistillationEngine
            if self._engine:
                p = self._engine._add_principle(
                    principle=text, source="llm_distill",
                    category=category, initial_score=0.6,
                    tags=["llm_distilled", category],
                )
                if p:
                    principles.append(p)

        logger.info("llm_distill_done", input_count=len(trajectories), output_count=len(principles))
        return principles

    def _build_summaries(self, trajectories: list[dict]) -> str:
        """构建轨迹摘要——每条约 200 字。"""
        parts: list[str] = []
        for i, t in enumerate(trajectories, 1):
            traj = t.get("trajectory", t)
            steps = t.get("steps", [])
            goal = traj.get("goal", "未知")[:100]
            outcome = traj.get("final_outcome", "?")
            quality = traj.get("quality_score", 0)
            actions = [s.get("action", "") for s in steps if s.get("action")]
            action_summary = " → ".join(actions[-5:]) if actions else "无动作"
            parts.append(
                f"{i}. Goal: {goal}\n   Outcome: {outcome}(score={quality})\n   Actions: {action_summary}"
            )
        return "\n\n".join(parts)
