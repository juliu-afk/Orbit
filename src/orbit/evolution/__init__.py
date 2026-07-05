"""自进化与对齐模块 (Phase C).

对标: EvolveR (2025), ANCHOR, AgentEvolver (阿里通义 2025)

Phase C (Agent 五大能力追赶): v0.30-v0.31
  - C1. 离线自蒸馏引擎——执行轨迹 → 可复用策略原则
  - C2. ANCHOR 对齐护栏——自进化各阶段注入人工监督检查点
"""

from orbit.evolution.distill import DistillationEngine, StrategyPrinciple
from orbit.evolution.anchor import AnchorGuard, AnchorCheckpoint, SupervisionResult

__all__ = [
    "DistillationEngine",
    "StrategyPrinciple",
    "AnchorGuard",
    "AnchorCheckpoint",
    "SupervisionResult",
]
