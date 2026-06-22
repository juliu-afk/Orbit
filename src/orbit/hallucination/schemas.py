"""Step 4.1 防幻觉层数据模型与异常定义。

PRD 数据契约来源：docs/PRD+ADR_4阶段.md 代码块-1、代码块-2。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HallucinationLevel(StrEnum):
    """防幻觉层级枚举。L1-L4 属于 Step 4.1，L5-L8 属于 Step 4.2。"""

    L1_GRAPH = "l1_graph"
    L2_DYNAMIC = "l2_dynamic"
    L3_ENTROPY = "l3_entropy"
    L4_TYPE = "l4_type"


class ValidationResult(BaseModel):
    """单层验证结果。

    WHY 统一模型：调度器不需要知道每层内部实现，只判断 passed + 读 errors。
    """

    passed: bool
    level: HallucinationLevel
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # 扩展元数据：L1 存 missing_symbols，L3 存 avg_entropy，L4 存 error_lines
    metadata: dict[str, Any] = Field(default_factory=dict)


class L3EntropyConfig(BaseModel):
    """L3 熵监控配置（PRD Q1 决议：DeepSeek 0.75，Qwen 0.70）。

    WHY 模型级配置：不同模型 token 分布差异大，统一阈值误报率高。
    """

    window_size: int = Field(10, ge=1, description="滑动窗口大小")
    threshold: float = Field(0.75, ge=0.0, le=1.0, description="熵阈值")
    fallback_enabled: bool = Field(True, description="无 logprobs 时降级为重复度检测")


# ---- 异常定义 ----
# WHY 分层异常：调度器根据异常类型决定重试策略（图谱错误 → 换提示词重试，
# 熵过高 → 取消并熔断，类型错误 → 修正后重试）


class HallucinationError(Exception):
    """防幻觉异常基类。"""


class GraphReferenceError(HallucinationError):
    """L1: 代码引用了代码图谱中不存在的符号。"""

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        super().__init__(f"Symbols not found in code graph: {', '.join(symbols)}")


class HighEntropyError(HallucinationError):
    """L3: LLM 生成过程中熵超过阈值，表示输出不确定性高。"""

    def __init__(self, entropy: float, threshold: float):
        self.entropy = entropy
        self.threshold = threshold
        super().__init__(f"Entropy {entropy:.3f} exceeded threshold {threshold}")


class TypeCheckError(HallucinationError):
    """L4: mypy 静态类型检查发现错误。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Type check failed: {'; '.join(errors[:3])}")


class DynamicCallError(HallucinationError):
    """L2: 沙箱运行时追踪到未注册在图谱中的动态调用。"""

    def __init__(self, calls: list[str]):
        self.calls = calls
        super().__init__(f"Dynamic calls not found in code graph: {', '.join(calls)}")
