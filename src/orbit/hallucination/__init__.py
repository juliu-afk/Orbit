"""Step 4.1 防幻觉层 L1-L4：纵深防御体系。

L1 图谱引用验证 → L2 动态追踪 → L3 概率熵监控 → L4 静态类型检查。
覆盖 LLM 代码生成全链路：生成前(L4) → 生成中(L3) → 生成后(L1) → 运行时(L2)。

使用方式（调度器调用）：
    from orbit.hallucination import L1GraphValidator, ValidationResult
    validator = L1GraphValidator(code_engine)
    result = await validator.validate(code)
    if not result.passed:
        raise GraphReferenceError(result.errors)
"""

from orbit.hallucination.l1_graph import L1GraphValidator
from orbit.hallucination.l2_dynamic import L2DynamicTracer
from orbit.hallucination.l3_entropy import L3EntropyMonitor
from orbit.hallucination.l4_type import L4TypeValidator
from orbit.hallucination.schemas import (
    DynamicCallError,
    GraphReferenceError,
    HallucinationError,
    HallucinationLevel,
    HighEntropyError,
    L3EntropyConfig,
    TypeCheckError,
    ValidationResult,
)

__all__ = [
    # 验证器
    "L1GraphValidator",
    "L2DynamicTracer",
    "L3EntropyMonitor",
    "L4TypeValidator",
    # 数据模型
    "HallucinationLevel",
    "L3EntropyConfig",
    "ValidationResult",
    # 异常
    "DynamicCallError",
    "GraphReferenceError",
    "HallucinationError",
    "HighEntropyError",
    "TypeCheckError",
]
