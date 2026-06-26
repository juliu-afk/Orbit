"""AgentModelResolver——5 级优先级解析 Agent 实际使用的模型。

优先级（从高到低）:
    1. CC_SWITCH force 模式——运维强制覆盖
    2. 环境变量 AGENT_{ROLE}_MODEL——为特定 Agent 预设
    3. CC_SWITCH no-force 模式——运维建议
    4. RouterAgent 推荐——基于任务复杂度
    5. 系统默认 DEFAULT_LLM_MODEL——全局兜底

所有模型变更来源记录在 ResolvedModel.source 中，供审计使用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import structlog

from orbit.router.agent import FALLBACK_MODEL, TIER_MODEL_MAP, ModelTier, RouterDecision
from orbit.router.cc_switch import parse_cc_switch

logger = structlog.get_logger("orbit.router.resolver")


@dataclass
class ResolvedModel:
    model: str  # LiteLLM 模型 ID（空字符串 = 本地规则引擎，不调 LLM）
    tier: ModelTier | None
    source: str  # "cc_switch_force" | "environment" | "cc_switch" | "router" | "default"
    reason: str
    is_forced: bool = False


class AgentModelResolver:
    """按优先级解析 Agent 实际使用的模型。

    用法:
        resolver = AgentModelResolver()
        resolved = await resolver.resolve(
            agent_name="DeveloperAgent",
            router_decision=RouterDecision(tier=ModelTier.TIER_2, ...)
        )
    """

    def __init__(self):
        self._cache: dict[str, ResolvedModel] = {}

    async def resolve(
        self,
        agent_name: str,
        router_decision: RouterDecision | None = None,
    ) -> ResolvedModel:
        """按 5 级优先级解析模型配置。"""

        # 1. CC_SWITCH force 模式——最高优先级
        cc_config = parse_cc_switch()
        for entry in cc_config.entries:
            if entry.is_force and (
                entry.agent_name == "all" or entry.agent_name.lower() == agent_name.lower()
            ):
                result = ResolvedModel(
                    model=entry.model,
                    tier=None,
                    source="cc_switch_force",
                    reason=f"CC_SWITCH force: {entry.agent_name}:{entry.model}",
                    is_forced=True,
                )
                self._cache[agent_name] = result
                return result

        # 2. 环境变量 AGENT_{ROLE}_MODEL
        env_key = f"AGENT_{agent_name.upper()}_MODEL"
        env_model = os.getenv(env_key)
        if env_model:
            result = ResolvedModel(
                model=env_model,
                tier=None,
                source="environment",
                reason=f"环境变量 {env_key}={env_model}",
                is_forced=False,
            )
            self._cache[agent_name] = result
            return result

        # 3. CC_SWITCH no-force 模式
        for entry in cc_config.entries:
            if not entry.is_force and (
                entry.agent_name == "all" or entry.agent_name.lower() == agent_name.lower()
            ):
                result = ResolvedModel(
                    model=entry.model,
                    tier=None,
                    source="cc_switch",
                    reason=f"CC_SWITCH: {entry.agent_name}:{entry.model}",
                    is_forced=False,
                )
                self._cache[agent_name] = result
                return result

        # 4. RouterAgent 推荐
        if router_decision and router_decision.tier != ModelTier.TIER_0:
            model = TIER_MODEL_MAP.get(router_decision.tier.value, "")
            result = ResolvedModel(
                model=model,
                tier=router_decision.tier,
                source="router",
                reason=f"RouterAgent: {router_decision.reason}",
                is_forced=False,
            )
            self._cache[agent_name] = result
            return result

        # Tier 0: 本地规则引擎，不调 LLM
        if router_decision and router_decision.tier == ModelTier.TIER_0:
            result = ResolvedModel(
                model="",
                tier=ModelTier.TIER_0,
                source="router",
                reason="本地规则引擎，无需 LLM 调用",
                is_forced=False,
            )
            self._cache[agent_name] = result
            return result

        # 5. 系统默认
        default_model = os.getenv("DEFAULT_LLM_MODEL", "")
        if not default_model:
            default_model = TIER_MODEL_MAP.get(ModelTier.TIER_3.value, FALLBACK_MODEL)

        result = ResolvedModel(
            model=default_model,
            tier=None,
            source="default",
            reason=f"系统默认模型"
            + (
                f" ({os.getenv('DEFAULT_LLM_MODEL', '')})" if os.getenv("DEFAULT_LLM_MODEL") else ""
            ),
            is_forced=False,
        )
        self._cache[agent_name] = result
        return result

    def get_cached(self, agent_name: str) -> ResolvedModel | None:
        """获取缓存的解析结果。"""
        return self._cache.get(agent_name)
