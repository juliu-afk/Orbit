"""RoutingStrategy 单元测试——LLM 模型路由选择。

Phase 3 组 1 (AC18.3): 覆盖 cheapest/fastest/best/agent 四种策略。
"""

from __future__ import annotations


class TestRoutingCheapest:
    """cheapest 策略——选成本最低模型。"""

    def test_cheapest_picks_free_model(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(RoutingStrategy.CHEAPEST)
        # GLM-4.7-flash 和 GLM-5.2 都是免费，但 flash 成本更低（速度为 1）
        # 实际排序: 免费模型优先
        cost_free_models = ["openai/glm-5.2", "openai/glm-4.7-flash"]
        assert decision.model in cost_free_models
        assert decision.strategy == RoutingStrategy.CHEAPEST

    def test_cheapest_with_limited_models(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        # 只有付费模型可选
        decision = select_model(
            RoutingStrategy.CHEAPEST,
            available_models=["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"],
        )
        # DS V4 Flash 比 DS V4 Pro 便宜
        assert decision.model == "deepseek/deepseek-v4-flash"


class TestRoutingFastest:
    """fastest 策略——选延迟最低模型。"""

    def test_fastest_picks_flash(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(RoutingStrategy.FASTEST)
        # Flash 类模型速度 rank 1
        assert "flash" in decision.model.lower()
        assert decision.strategy == RoutingStrategy.FASTEST


class TestRoutingBestQuality:
    """best 策略——选最强推理模型。"""

    def test_best_picks_top_quality(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(RoutingStrategy.BEST_QUALITY)
        # GLM-5.2 质量 rank 1
        assert decision.model == "openai/glm-5.2"
        assert decision.strategy == RoutingStrategy.BEST_QUALITY


class TestRoutingAgentDefault:
    """agent 策略——委托给 Resolver。"""

    def test_agent_default_returns_empty_model(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(RoutingStrategy.AGENT_DEFAULT)
        assert decision.model == ""
        assert decision.reason == "delegated_to_agent_resolver"
        assert decision.strategy == RoutingStrategy.AGENT_DEFAULT


class TestRoutingEdgeCases:
    """边缘情况。"""

    def test_empty_model_list_fallback(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(RoutingStrategy.CHEAPEST, available_models=[])
        # 回退到最可靠的
        assert decision.model == "deepseek/deepseek-v4-pro"
        assert "fallback" in decision.reason

    def test_single_model_available(self):
        from orbit.gateway.routing import RoutingStrategy, select_model

        decision = select_model(
            RoutingStrategy.BEST_QUALITY,
            available_models=["deepseek/deepseek-v4-flash"],
        )
        assert decision.model == "deepseek/deepseek-v4-flash"

    def test_decision_is_serializable(self):
        from orbit.gateway.routing import RoutingDecision, RoutingStrategy

        d = RoutingDecision(
            strategy=RoutingStrategy.CHEAPEST,
            model="openai/glm-4.7-flash",
            reason="cheapest_model_cost_0.000000_per_1k",
        )
        dumped = d.model_dump()
        assert dumped["strategy"] == "cheapest"
        assert dumped["model"] == "openai/glm-4.7-flash"
