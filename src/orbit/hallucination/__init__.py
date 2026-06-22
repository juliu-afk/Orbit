"""Step 4.1/4.2 防幻觉层 L1-L8：纵深防御体系。

L1 图谱验证 → L2 动态追踪 → L3 熵监控 → L4 类型检查
L5 Z3 形式化 → L6 合约验证 → L7 沙箱执行 → L8 配置漂移

全链路：生成前(L4)→生成中(L3)→生成后(L1)→运行时(L2)→
深度验证(L5-L8)。
"""

from orbit.hallucination.l1_graph import L1GraphValidator
from orbit.hallucination.l2_dynamic import L2DynamicTracer
from orbit.hallucination.l3_entropy import L3EntropyMonitor
from orbit.hallucination.l4_type import L4TypeValidator
from orbit.hallucination.l5_z3 import L5Z3Validator
from orbit.hallucination.l6_contract import L6ContractValidator
from orbit.hallucination.l7_runtime import L7RuntimeValidator
from orbit.hallucination.l8_config import L8ConfigValidator
from orbit.hallucination.schemas import (
    DynamicCallError,
    GraphReferenceError,
    HallucinationError,
    HallucinationLevel,
    HighEntropyError,
    L3EntropyConfig,
    L5ValidationResult,
    L5VerificationError,
    L6ContractMatch,
    L6ContractViolationError,
    L7RuntimeError,
    L8DriftDetectedError,
    L8DriftReport,
    TypeCheckError,
    ValidationResult,
)

__all__ = [
    "L1GraphValidator",
    "L2DynamicTracer",
    "L3EntropyMonitor",
    "L4TypeValidator",
    "L5Z3Validator",
    "L6ContractValidator",
    "L7RuntimeValidator",
    "L8ConfigValidator",
    "HallucinationLevel",
    "L3EntropyConfig",
    "L5ValidationResult",
    "L6ContractMatch",
    "L8DriftReport",
    "ValidationResult",
    "DynamicCallError",
    "GraphReferenceError",
    "HallucinationError",
    "HighEntropyError",
    "L5VerificationError",
    "L6ContractViolationError",
    "L7RuntimeError",
    "L8DriftDetectedError",
    "TypeCheckError",
]
