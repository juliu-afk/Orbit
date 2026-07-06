"""需求澄清 Agent——数据模型。

V5 结构契约：Agent 输出的结构化 PRD schema + V1-V3 校验结果模型。
"""

from pydantic import BaseModel, Field


class StructuredPRD(BaseModel):
    """结构化 PRD——ClarifierAgent 输出的需求文档。

    V5 校验直接 model_validate_json，不符合 schema 即拦截。
    """

    goal: str = ""
    scope: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    # 仅当需要用户选验收标准时填，否则空数组（PRD 验收候选策略）
    acceptance_options: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """V1-V3 校验结果。

    passed=False 时 failed_layer 和 reasons 告诉 Agent 本轮要问什么。
    """

    passed: bool
    failed_layer: str = ""  # V1 | V2 | V3 | ""
    reasons: list[str] = Field(default_factory=list)
