"""RouterAgent——PLANNING 阶段评估任务复杂度，输出推荐模型级别。

5 维度评分（权重可配置）:
    1. 涉及文件数 (30%)
    2. 修改类型 (25%)
    3. 风险等级 (25%)
    4. Agent 角色 (15%)
    5. 历史相似任务 (5%)

输出: RouterDecision {tier: Tier 0-3, confidence, reason}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import structlog

from orbit.router.weights import ScoreWeights

logger = structlog.get_logger("orbit.router.agent")

# LiteLLM 模型 ID 映射
TIER_MODEL_MAP: dict[str, str] = {
    "tier_0": "",  # 本地规则引擎，无 LLM 调用
    "tier_1": "deepseek/deepseek-v4-flash",  # DS Flash——轻量·省钱
    "tier_2": "deepseek/deepseek-v4-pro",  # DS V4 Pro——中档·标准
    "tier_3": "openai/glm-5.2",  # GLM-5.2——最强·Coding Plan
}

FALLBACK_MODEL = "openai/glm-4.7-flash"  # 统一降级兜底（免费）


class ModelTier(StrEnum):
    TIER_0 = "tier_0"  # 本地规则引擎——零 LLM 调用
    TIER_1 = "tier_1"  # DS Flash——轻量任务
    TIER_2 = "tier_2"  # DS V4 Pro——中等任务
    TIER_3 = "tier_3"  # GLM-5.2——最强任务


# Tier 判定阈值
TIER_THRESHOLDS: list[tuple[int, ModelTier]] = [
    (71, ModelTier.TIER_3),
    (40, ModelTier.TIER_2),
    (15, ModelTier.TIER_1),
    (0, ModelTier.TIER_0),
]

# 核心模块关键词——高风险
CORE_MODULES: list[str] = [
    "scheduler",
    "orchestrator",
    "checkpoint",
    "gateway",
    "hallucination",
    "compliance",
    "resource_guard",
    "sandbox",
    "payment",
    "security",
    "auth",
    "encryption",
]

# Agent 角色基础分
ROLE_BASE_SCORES: dict[str, int] = {
    "config_manager": 0,
    "clarifier": 20,
    "developer": 50,
    "reviewer": 60,
    "qa": 60,
    "architect": 100,
}


@dataclass
class ComplexityScore:
    """任务复杂度评分——0-100。"""

    total: float = 0.0
    file_count_score: float = 0.0
    change_type_score: float = 0.0
    risk_score: float = 0.0
    agent_role_score: float = 0.0
    historical_score: float = 0.0


@dataclass
class RouterDecision:
    tier: ModelTier
    reason: str
    confidence: float  # 0-1
    fallback_tier: ModelTier | None = None


class RouterAgent:
    """PLANNING 阶段评估任务复杂度，推荐模型级别。

    用法:
        agent = RouterAgent(weights=ScoreWeights.from_env())
        decision = await agent.evaluate(
            file_count=5, change_type="multi_file", risk="medium",
            agent_role="developer", has_similar_history=False
        )
    """

    def __init__(self, weights: ScoreWeights | None = None):
        self.weights = weights or ScoreWeights.from_env()

    async def evaluate(
        self,
        file_count: int = 1,
        change_type: str = "single_file",
        risk: str = "low",
        agent_role: str = "developer",
        has_similar_history: bool = False,
    ) -> RouterDecision:
        """评估任务复杂度并输出模型推荐。"""
        reasons: list[str] = []

        # 1. 文件数评分
        if file_count == 1:
            f_score = 0.0
            reasons.append("单文件")
        elif file_count <= 5:
            f_score = 50.0
            reasons.append(f"{file_count} 个文件")
        else:
            f_score = 100.0
            reasons.append(f"{file_count} 个文件(多)")

        # 2. 修改类型评分
        ct_map = {
            "config": 0.0,
            "comment": 0.0,
            "format": 10.0,
            "single_line": 10.0,
            "single_function": 35.0,
            "single_file": 45.0,
            "multi_file": 70.0,
            "multi_module": 100.0,
        }
        c_score = ct_map.get(change_type, 50.0)
        reasons.append(f"修改类型: {change_type}")

        # 3. 风险评分
        risk_map = {"low": 0.0, "medium": 50.0, "high": 100.0}
        r_score = risk_map.get(risk, 50.0)
        if r_score > 0:
            reasons.append(f"风险: {risk}")

        # 4. Agent 角色评分
        a_score = float(ROLE_BASE_SCORES.get(agent_role, 50))
        reasons.append(f"角色: {agent_role}")

        # 5. 历史相似任务——有成功先例可降级
        h_score = -30.0 if has_similar_history else 0.0
        if h_score < 0:
            reasons.append("有历史先例，可降级")

        # 加权计算 → clamp 到 [0, 100]
        w = self.weights
        total = (
            f_score * w.files / 100.0
            + c_score * w.change / 100.0
            + r_score * w.risk / 100.0
            + a_score * w.role / 100.0
            + h_score * w.history / 100.0
        )
        total = max(0.0, min(100.0, total))

        # 判定 Tier
        tier = self._score_to_tier(total)

        # 置信度——基于总分是否在边界附近
        confidence = self._calc_confidence(total, tier)

        # 降级 Tier——下一级
        tier_order = [ModelTier.TIER_0, ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3]
        idx = tier_order.index(tier)
        fallback = tier_order[idx - 1] if idx > 0 else None

        logger.info(
            "router_decision",
            total_score=round(total, 1),
            tier=tier.value,
            confidence=round(confidence, 2),
            reasons="; ".join(reasons),
        )

        return RouterDecision(
            tier=tier,
            reason="; ".join(reasons),
            confidence=confidence,
            fallback_tier=fallback,
        )

    def _score_to_tier(self, total: float) -> ModelTier:
        """总分 → Tier 映射。"""
        for threshold, tier in TIER_THRESHOLDS:
            if total >= threshold:
                return tier
        return ModelTier.TIER_0

    def _calc_confidence(self, total: float, tier: ModelTier) -> float:
        """计算置信度——分数离阈值越远越自信。"""
        tier_order = [ModelTier.TIER_0, ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3]
        thresholds = [0, 15, 40, 71]
        idx = tier_order.index(tier)
        threshold = thresholds[idx]
        distance = abs(total - threshold)
        # 离阈值 0 分 → 0.5，离阈值 30+ 分 → 1.0
        return min(1.0, 0.5 + distance / 40.0)
