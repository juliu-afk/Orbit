"""自进化与对齐模块 (Phase C+E).

对标: EvolveR (2025), ANCHOR, AgentEvolver (阿里通义 2025)

Phase C: 离线自蒸馏 + 对齐护栏
Phase E: LLM语义蒸馏 + GRPO评分 + 策略注入
"""

from orbit.evolution.anchor import AnchorCheckpoint, AnchorGuard, SupervisionResult
from orbit.evolution.distill import DistillationEngine, StrategyPrinciple
from orbit.evolution.grpo import GRPOScorer
from orbit.evolution.inject import PromptInjector
from orbit.evolution.llm_distill import LLMDistiller

__all__ = [
    "DistillationEngine",
    "StrategyPrinciple",
    "AnchorGuard",
    "AnchorCheckpoint",
    "SupervisionResult",
    "LLMDistiller",
    "GRPOScorer",
    "PromptInjector",
]
