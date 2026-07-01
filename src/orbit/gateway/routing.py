"""LLM 路由策略——按任务/成本/速度选择模型。

对标 OpenClaw agent_launch 的 per-provider 模型选择。
WHY 独立于 client.py: 路由策略是纯函数，方便测试和扩展。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class RoutingStrategy(StrEnum):
    """路由策略枚举。"""

    CHEAPEST = "cheapest"  # 成本最低（GLM-4.7 Flash 免费）
    FASTEST = "fastest"  # 延迟最低（Flash 类模型）
    BEST_QUALITY = "best"  # 最强推理（GLM-5.2 / DS V4 Pro）
    AGENT_DEFAULT = "agent"  # 按 Agent 角色默认（现有行为——走 Resolver）


class RoutingDecision(BaseModel):
    """路由决策结果。"""

    strategy: RoutingStrategy
    model: str
    reason: str = ""


# 模型→成本映射（USD/1K tokens）
_MODEL_COSTS: dict[str, float] = {
    "deepseek/deepseek-v4-pro": 0.001305,
    "deepseek/deepseek-v4-flash": 0.00042,
    "openai/glm-5.2": 0.0,  # 免费（Coding Plan）
    "openai/glm-4.7-flash": 0.0,  # 免费（Coding Plan）
}

# 模型→延迟排名（越低越快）
_MODEL_SPEED: dict[str, int] = {
    "deepseek/deepseek-v4-flash": 1,
    "openai/glm-4.7-flash": 1,
    "openai/glm-5.2": 2,
    "deepseek/deepseek-v4-pro": 3,
}

# 模型→质量排名（越低越好）
_MODEL_QUALITY: dict[str, int] = {
    "openai/glm-5.2": 1,
    "deepseek/deepseek-v4-pro": 2,
    "deepseek/deepseek-v4-flash": 3,
    "openai/glm-4.7-flash": 4,
}


def select_model(
    strategy: RoutingStrategy,
    available_models: list[str] | None = None,
    price_multiplier: float = 1.0,  # D13: 当前时段价格倍数——低峰 <1.0
) -> RoutingDecision:
    """纯函数——按策略选最佳模型。

    Args:
        strategy: 路由策略
        available_models: 可用模型列表（None = 全部可用）

    Returns:
        RoutingDecision——选中的模型和理由。
    """
    models = available_models if available_models is not None else list(_MODEL_COSTS.keys())

    if not models:
        # 回退——无可用模型时用最可靠的
        return RoutingDecision(
            strategy=strategy,
            model="deepseek/deepseek-v4-pro",
            reason="empty_model_list_fallback_to_pro",
        )

    if strategy == RoutingStrategy.CHEAPEST:
        # D13: 按有效成本（基础价格 × 时段倍数）升序
        sorted_models = sorted(
            models,
            key=lambda m: _MODEL_COSTS.get(m, 999.0) * price_multiplier,
        )
        chosen = sorted_models[0]
        effective_cost = _MODEL_COSTS.get(chosen, 0) * price_multiplier
        return RoutingDecision(
            strategy=strategy,
            model=chosen,
            reason=f"cheapest_model_effective_cost_{effective_cost:.6f}_per_1k",
        )

    if strategy == RoutingStrategy.FASTEST:
        sorted_models = sorted(models, key=lambda m: _MODEL_SPEED.get(m, 99))
        chosen = sorted_models[0]
        return RoutingDecision(
            strategy=strategy,
            model=chosen,
            reason=f"fastest_model_speed_rank_{_MODEL_SPEED.get(chosen, 0)}",
        )

    if strategy == RoutingStrategy.BEST_QUALITY:
        sorted_models = sorted(models, key=lambda m: _MODEL_QUALITY.get(m, 99))
        chosen = sorted_models[0]
        return RoutingDecision(
            strategy=strategy,
            model=chosen,
            reason=f"best_quality_rank_{_MODEL_QUALITY.get(chosen, 0)}",
        )

    # AGENT_DEFAULT——走现有 Resolver 逻辑，不在此处选
    return RoutingDecision(
        strategy=strategy,
        model="",  # 空字符串表示交由 Resolver 决定
        reason="delegated_to_agent_resolver",
    )
