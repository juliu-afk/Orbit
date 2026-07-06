"""Mode 数据模型——Pydantic 校验.

WHY Pydantic: mode.yaml 用户可编辑，必须在加载时校验。
校验失败 → ModeLoadError → 上游降级到默认行为。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionStrategy(StrEnum):
    """提问策略——grill-me 核心算法.

    depth_first:  完成一个决策分支再开下一个（grill-me 默认）
    breadth_first: 先扫所有分支顶层，再逐层深入
    mixed: 关键分支深度优先，次要广度优先
    """

    DEPTH_FIRST = "depth_first"
    BREADTH_FIRST = "breadth_first"
    MIXED = "mixed"


class BehaviorConfig(BaseModel):
    """Agent 行为参数——从 mode.yaml 加载，注入到 Agent 实例.

    WHY 独立模型: 行为参数与模式元数据分离，Agent 只关心 behavior。
    """

    question_strategy: QuestionStrategy = QuestionStrategy.DEPTH_FIRST
    max_questions_per_branch: int = Field(default=20, ge=1, le=100)
    require_recommendation: bool = True  # 每个问题必须带推荐答案
    codebase_first: bool = True  # 能查代码就不问用户
    auto_upgrade_context: bool = True  # 工具调用失败时自动升级上下文阶段


class ModeConfig(BaseModel):
    """模式文件顶层结构——对应单个 mode.yaml.

    示例 (clarify/mode.yaml):
        name: clarify
        version: 1
        description: "需求澄清——深度优先决策树遍历"
        applies_to: [PARSING]
        behavior:
          question_strategy: depth_first
          max_questions_per_branch: 20
        references:
          - question-tree.md
    """

    name: str = Field(..., min_length=1, description="模式名，对应目录名")
    version: int = Field(default=1, ge=1)
    description: str = ""
    applies_to: list[str] = Field(default_factory=list, description="适用的状态机阶段")
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    references: list[str] = Field(default_factory=list, description="按需加载的文件名")
