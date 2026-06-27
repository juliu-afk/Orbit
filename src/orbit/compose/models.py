"""Compose 数据模型——对标 MiMo Code compose/.bundle/ SKILL.md frontmatter.

WHY YAML frontmatter: 技能元数据与 markdown body 分离——
机器读 frontmatter 做路由，人类读 body 做理解。
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, Field


class SkillPhase(StrEnum):
    """技能执行阶段。"""
    PLAN = "plan"         # 方案设计
    IMPLEMENT = "implement"  # 代码实现
    REVIEW = "review"     # 代码审查
    VERIFY = "verify"     # 验证测试
    MERGE = "merge"       # 合并工作流


class Skill(BaseModel):
    """SKILL.md 技能定义。

    YAML frontmatter → Skill pydantic model。
    """

    name: str = Field(..., description="技能名称（唯一标识）")
    description: str = Field("", description="技能描述")
    phase: SkillPhase = Field(..., description="执行阶段")
    tools: list[str] = Field(default_factory=list, description="需要的工具列表")
    agent_role: str = Field("developer", description="默认 Agent 角色")
    body: str = Field("", description="Markdown body——技能指令")

    # 技能文件路径（加载时填充）
    path: str = ""


class Spec(BaseModel):
    """spec 文件——用户编写的任务规格。

    对标 MiMo compose:plan 的输入格式。
    """

    title: str = Field(..., min_length=1, description="项目/任务标题")
    description: str = Field("", description="任务描述")
    tasks: list[Task] = Field(default_factory=list, description="子任务列表")
    language: str = Field("python", description="编程语言")
    constraints: list[str] = Field(default_factory=list, description="约束条件")


class Task(BaseModel):
    """spec 中的单个任务。

    对标 MiMo compose:subagent 的 task 结构。
    """

    id: str = Field(..., description="任务 ID（spec 内唯一）")
    description: str = Field(..., min_length=1, description="任务描述")
    agent_role: str = Field("developer", description="执行 Agent 角色")
    skill: str = Field("", description="使用的技能名称")
    depends_on: list[str] = Field(default_factory=list, description="依赖的任务 ID 列表")

    # 执行状态（运行时填充）
    MAX_RETRIES: ClassVar[int] = 2
