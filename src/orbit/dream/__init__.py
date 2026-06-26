"""/dream 自进化模块 (Phase 2 AC10).

5 阶段 LLM 合并 + 去重 + 验证 + 7 天自动触发.
"""

from orbit.dream.engine import DreamEngine
from orbit.dream.models import DreamConfig, DreamResult, DreamStage, DreamStatus
from orbit.dream.verifier import DreamVerifier

__all__ = [
    "DreamConfig",
    "DreamEngine",
    "DreamResult",
    "DreamStage",
    "DreamStatus",
    "DreamVerifier",
]
