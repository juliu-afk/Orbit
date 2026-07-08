"""因果改进建议 + LLM 解释生成 (P1).

WHY LLM 仅做解释:
  DoWhy GCM 输出数值异常分数——对运维/开发者不可读。
  LLM 将数值翻译为自然语言解释——"agent_role=developer 贡献了 72% 异常"
  LLM 不参与因果计算——避免幻觉污染因果链。

用法:
    recommender = CausalRecommender(model_manager, llm_client)
    explanation = await recommender.explain(root_cause)
    suggestions = await recommender.recommend(root_cause)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.causal.graph import CausalModelManager
    from orbit.causal.models import RootCause
    from orbit.gateway.client import LLMClient

import structlog

from pydantic import BaseModel, Field

logger = structlog.get_logger("orbit.causal.recommend")

# LLM 解释 Prompt——输入异常分数，输出人类可读解释
EXPLANATION_PROMPT = """你是一个因果推理助手。以下是任务失败后 DoWhy GCM 识别的根因分析结果：

任务 ID: {task_id}
异常归因（分数越高 = 越可能是根因）：
{causes_text}

请用中文简洁解释：
1. 最可能的根因是什么（1 句话）
2. 为什么会是这个原因（1 句话，基于变量间的因果逻辑）
3. 建议怎么做（1 句话）

只输出解释，不要 JSON。不超过 150 字。"""

# 反事实 Prompt——基于因果效应生成改进建议
RECOMMENDATION_PROMPT = """你是一个因果推理助手。以下是 DoWhy GCM 识别的任务失败根因：

{explanation}

请输出 3 条具体的改进建议（每条 1 句话，不超过 30 字），按预期效果排序。
输出 JSON 数组: ["建议1", "建议2", "建议3"]"""


class Recommendation(BaseModel):
    """单条改进建议。"""
    action: str = ""           # 具体动作
    from_value: str = ""       # 当前值
    to_value: str = ""         # 建议值
    expected_gain_pct: float = Field(0.0, ge=0.0)  # 预期提升百分比
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class CausalRecommender:
    """因果改进建议生成器——反事实 + LLM 解释。

    P0: 仅数值反事实（不需要 LLM）
    P1: LLM 解释 + 建议生成
    """

    def __init__(
        self,
        model: CausalModelManager,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._model = model
        self._llm = llm_client

    async def explain(self, root_cause: RootCause) -> str:
        """LLM 生成人类可读根因解释。

        LLM 失败时降级为纯数值文本——不影响因果链的正确性。
        """
        if not root_cause.causes:
            return "无显著根因。建议人工检查任务轨迹。"

        # 构建数值解释（作为 LLM 输入或降级输出）
        causes_text = "\n".join(
            f"  - {c.variable}: 异常分数 {c.anomaly_score:.3f}"
            for c in root_cause.causes[:5]
        )
        numerical = (
            f"根因分析（DoWhy GCM, 置信度={root_cause.confidence:.0%}）：\n"
            f"{causes_text}\n"
            f"最高异常分数: {root_cause.causes[0].variable} "
            f"({root_cause.causes[0].anomaly_score:.3f})"
        )

        # 无 LLM → 返回数值报告
        if self._llm is None:
            return numerical

        # 有 LLM → 生成人类可读解释
        try:
            prompt = EXPLANATION_PROMPT.format(
                task_id=root_cause.task_id,
                causes_text=causes_text,
            )
            from orbit.gateway.schemas import LLMRequest
            req = LLMRequest(
                prompt=prompt,
                system_prompt="你是因果推理助手。用中文输出简洁解释。",
                task_type="structured_output",
            )
            result = await self._llm.generate(req, task_id="causal_explain")
            return result.content.strip() or numerical
        except Exception as e:
            logger.warning("llm_explain_failed", error=str(e))
            return numerical

    async def recommend(self, root_cause: RootCause) -> list[Recommendation]:
        """基于根因生成具体改进建议。

        先用 do-calculus 计算因果效应，再用 LLM 翻译为可执行操作。
        LLM 失败时降级为固定映射（agent→switch_agent, tier→upgrade_tier）。
        """
        if not root_cause.causes:
            return []

        # 从因果图读边数据（无需 LLM——纯数据查询）
        recommendations = self._heuristic_recommendations(root_cause)

        # P1: LLM 优化建议文本
        if self._llm is not None and root_cause.top_cause:
            try:
                enhanced = await self._enhance_with_llm(
                    root_cause, recommendations)
                if enhanced:
                    return enhanced
            except Exception:
                logger.warning("llm_enhance_failed", exc_info=True)
                # 降级——返回未增强的建议

        return recommendations

    # ── 内部 ──────────────────────────────────────────

    def _heuristic_recommendations(
        self, root_cause: RootCause,
    ) -> list[Recommendation]:
        """固定映射——将变量名翻译为改进建议（LLM 不可用时的降级）。"""
        action_map: dict[str, tuple[str, str, str]] = {
            "agent_role":  ("switch_agent", "developer", "architect"),
            "model_tier":  ("upgrade_tier", "", "tier_2"),
            "tool_error_rate": ("reduce_tool_complexity", "", ""),
            "total_turns": ("add_early_stop", "", ""),
            "latency":     ("simplify_prompt", "", ""),
            "quality_score": ("increase_review_depth", "", ""),
        }
        results: list[Recommendation] = []
        for c in root_cause.causes[:3]:
            action_info = action_map.get(c.variable)
            if action_info:
                results.append(Recommendation(
                    action=action_info[0],
                    from_value=action_info[1],
                    to_value=action_info[2],
                    expected_gain_pct=round(c.anomaly_score * 100, 1),
                    confidence=root_cause.confidence,
                ))
        return results

    async def _enhance_with_llm(
        self, root_cause: RootCause,
        base: list[Recommendation],
    ) -> list[Recommendation] | None:
        """LLM 增强——将固定映射的建议文本替换为 LLM 生成的精准文本。"""
        assert self._llm is not None
        explanation = await self.explain(root_cause)
        prompt = RECOMMENDATION_PROMPT.format(explanation=explanation)
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(
            prompt=prompt,
            system_prompt="输出 JSON 数组。",
            task_type="structured_output",
        )
        result = await self._llm.generate(req, task_id="causal_recommend")
        suggestions = json.loads(result.content.strip())
        if not isinstance(suggestions, list):
            return None

        # 用 LLM 文本替换固定映射的 action 文本
        for i, r in enumerate(base):
            if i < len(suggestions):
                r.action = str(suggestions[i])
        return base
