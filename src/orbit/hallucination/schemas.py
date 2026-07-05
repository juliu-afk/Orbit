"""Step 4.1/4.2 防幻觉层数据模型与异常定义。

PRD 数据契约来源：docs/PRD+ADR_4阶段.md 代码块-1/2/5/6。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HallucinationLevel(StrEnum):
    """防幻觉层级枚举。L1-L4 属于 Step 4.1，L5-L8 属于 Step 4.2。"""

    L1_GRAPH = "l1_graph"
    L2_DYNAMIC = "l2_dynamic"
    L3_ENTROPY = "l3_entropy"
    L4_TYPE = "l4_type"
    L5_Z3 = "l5_z3"
    L6_CONTRACT = "l6_contract"
    L7_RUNTIME = "l7_runtime"
    L8_CONFIG = "l8_config"


class ValidationResult(BaseModel):
    """单层验证结果。"""

    passed: bool
    level: HallucinationLevel
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class L3EntropyConfig(BaseModel):
    """L3 熵监控配置（PRD Q1 决议：DeepSeek 0.75，GLM 0.73）。"""

    window_size: int = Field(10, ge=1, description="滑动窗口大小")
    threshold: float = Field(0.75, ge=0.0, le=1.0, description="熵阈值")
    fallback_enabled: bool = Field(True, description="无 logprobs 时降级为重复度检测")


# ---- Step 4.2 数据模型 ----


class L5ValidationResult(ValidationResult):
    """L5 Z3 验证结果。"""

    z3_status: str = "skipped"  # sat | unsat | unknown | timeout | skipped
    counterexample: dict[str, Any] | None = None


# ── CUA 模式迁移：反思式 CoT 结果模型 ──
# WHY 新增而非修改现有模型：反思对比是附加信号，不改动现有 pass/fail 判定。
# 三层各一个模型——L2 追踪函数调用预测、L4 行为预测、L5 契约自述。


class L2ReflectionResult(ValidationResult):
    """L2 反思式验证结果——Agent 预测函数调用 vs 实际追踪对比。

    deviation_score: 0.0 = 完全匹配，1.0 = 完全偏离。
    WHY 仅在预测非空时计算偏差：Agent 未提供预测 → 跳过对比，不阻断。
    """

    predicted_calls: list[str] = Field(default_factory=list)
    actual_calls: list[str] = Field(default_factory=list)
    deviation_score: float = Field(0.0, ge=0.0, le=1.0)
    unpredicted_calls: list[str] = Field(default_factory=list)  # 预测了但没调用
    unexpected_calls: list[str] = Field(default_factory=list)  # 调用了但没预测


class L4BehaviorResult(ValidationResult):
    """L4 行为反思验证结果——Agent 自述预期行为 vs 沙箱实际执行对比。

    WHY 不改变 mypy 判定：mypy 结果仍在父类 passed/errors 字段。
    本模型附加 behavior_match 和 behavior_diff 供后续分析。
    """

    predicted_behavior: str = ""
    actual_behavior: str = ""
    behavior_match: bool = True
    behavior_diff: str = ""


class L5ContractResult(L5ValidationResult):
    """L5 契约反思验证结果——Agent 自述契约 vs Z3 验证契约对比。

    WHY 继承 L5ValidationResult：保留 z3_status 和 counterexample。
    新增自述契约字段，contract_mismatch 标记自述 vs Z3 的矛盾。
    contract_mismatch=True 时 z3_status 仍由 Z3 独立判定，
    矛盾作为额外信号记录，不改变 passed 字段。
    """

    self_claimed_contract: str = ""
    z3_verified_contract: str = ""
    contract_mismatch: bool = False


class L6ContractMatch(BaseModel):
    """L6 单端点合约比对结果。"""

    endpoint: str
    method: str
    request_model: str
    response_model: str
    matched: bool
    differences: list[str] = Field(default_factory=list)


class L8DriftReport(BaseModel):
    """L8 配置漂移报告。"""

    file_path: str
    baseline_hash: str
    current_hash: str
    diff: str
    auto_fixed: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---- 异常定义 ----


class HallucinationError(Exception):
    """防幻觉异常基类。"""


class GraphReferenceError(HallucinationError):
    """L1: 代码引用了代码图谱中不存在的符号。"""

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        super().__init__(f"Symbols not found in code graph: {', '.join(symbols)}")


class DynamicCallError(HallucinationError):
    """L2: 沙箱运行时追踪到未注册在图谱中的动态调用。"""

    def __init__(self, calls: list[str]):
        self.calls = calls
        super().__init__(f"Dynamic calls not found in code graph: {', '.join(calls)}")


class HighEntropyError(HallucinationError):
    """L3: LLM 生成过程中熵超过阈值。"""

    def __init__(self, entropy: float, threshold: float):
        self.entropy = entropy
        self.threshold = threshold
        super().__init__(f"Entropy {entropy:.3f} exceeded threshold {threshold}")


class TypeCheckError(HallucinationError):
    """L4: mypy 静态类型检查发现错误。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Type check failed: {'; '.join(errors[:3])}")


class L5VerificationError(HallucinationError):
    """L5: Z3 验证失败（存在反例）。"""

    def __init__(self, counterexample: dict[str, Any] | None = None):
        self.counterexample = counterexample
        super().__init__(f"Z3 verification failed, counterexample: {counterexample}")


class L6ContractViolationError(HallucinationError):
    """L6: API 合约不一致。"""

    def __init__(self, endpoint: str, differences: list[str]):
        self.endpoint = endpoint
        self.differences = differences
        super().__init__(f"Contract violation at {endpoint}: {'; '.join(differences)}")


class L7RuntimeError(HallucinationError):
    """L7: 沙箱运行时测试失败。"""

    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__(f"Runtime test failures: {'; '.join(failures)}")


class L8DriftDetectedError(HallucinationError):
    """L8: 配置漂移检测。"""

    def __init__(self, file_path: str, diff: str):
        self.file_path = file_path
        self.diff = diff
        super().__init__(f"Config drift detected in {file_path}")
