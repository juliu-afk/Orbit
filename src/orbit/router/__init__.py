"""智能路由模块 (Step 2.3).

RouterAgent: PLANNING 阶段评估任务复杂度，输出推荐模型级别。
AgentModelResolver: 5 级优先级解析 Agent 实际使用的模型。
CC_SWITCH: 运维强制覆盖——解析 CC_SWITCH 环境变量。
"""

from orbit.router.agent import ModelTier, RouterAgent, RouterDecision, ComplexityScore
from orbit.router.resolver import AgentModelResolver, ResolvedModel
from orbit.router.cc_switch import CCSwitchConfig, CCSwitchEntry, parse_cc_switch
from orbit.router.weights import ScoreWeights

__all__ = [
    "ModelTier",
    "RouterAgent",
    "RouterDecision",
    "ComplexityScore",
    "AgentModelResolver",
    "ResolvedModel",
    "CCSwitchConfig",
    "CCSwitchEntry",
    "parse_cc_switch",
    "ScoreWeights",
]
