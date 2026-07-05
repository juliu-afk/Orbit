"""自进化与对齐模块 (Phase C+E+G).

Phase C: 离线自蒸馏 + 对齐护栏
Phase E: LLM语义蒸馏 + GRPO评分 + 策略注入
Phase G: GEPA Prompt进化 + SCOPE 双流记忆
"""

from orbit.evolution.anchor import AnchorCheckpoint, AnchorGuard, SupervisionResult
from orbit.evolution.distill import DistillationEngine, StrategyPrinciple
from orbit.evolution.gepa import GEPAEngine
from orbit.evolution.grpo import GRPOScorer
from orbit.evolution.inject import PromptInjector
from orbit.evolution.llm_distill import LLMDistiller
from orbit.evolution.scope import ScopeMemory

__all__ = [
    "DistillationEngine",
    "StrategyPrinciple",
    "AnchorGuard",
    "AnchorCheckpoint",
    "SupervisionResult",
    "LLMDistiller",
    "GRPOScorer",
    "PromptInjector",
    "GEPAEngine",
    "ScopeMemory",
]
