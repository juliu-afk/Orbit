"""Compose 数据模型——对标 MiMo Code compose/.bundle/ SKILL.md frontmatter.

WHY YAML frontmatter: 技能元数据与 markdown body 分离——
机器读 frontmatter 做路由，人类读 body 做理解。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SkillPhase(StrEnum):
    """技能执行阶段。"""

    PLAN = "plan"  # 方案设计
    IMPLEMENT = "implement"  # 代码实现
    REVIEW = "review"  # 代码审查
    VERIFY = "verify"  # 验证测试
    MERGE = "merge"  # 合并工作流


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

    RUNE 启发增强（Part C）:
    - signature: 函数签名——明确输入输出类型
    - behavior: WHEN/THEN 行为契约
    - tests: 必须通过的断言列表（注入 DeveloperAgent prompt）
    """

    id: str = Field(..., description="任务 ID（spec 内唯一）")
    description: str = Field(..., min_length=1, description="任务描述")
    agent_role: str = Field("developer", description="执行 Agent 角色")
    skill: str = Field("", description="使用的技能名称")
    depends_on: list[str] = Field(default_factory=list, description="依赖的任务 ID 列表")

    # ── RUNE 启发增强字段（均可选，向后兼容）─────────────
    signature: str = Field(
        "",
        description="函数签名——明确输入输出类型，如 async def create_user(db: AsyncSession, data: UserCreate) -> User",
    )
    behavior: list[str] = Field(
        default_factory=list,
        description="WHEN/THEN 行为契约，如 WHEN email 已存在 THEN raise DuplicateError",
    )
    tests: list[str] = Field(
        default_factory=list,
        description="必须通过的测试断言——注入 DeveloperAgent prompt 作为验收标准",
    )

    def has_rune_spec(self) -> bool:
        """是否包含 RUNE 风格规范。"""
        return bool(self.signature or self.behavior or self.tests)

    def build_acceptance_prompt(self) -> str:
        """构建验收标准 prompt 片段——注入 DeveloperAgent volatile 层。

        WHY 独立方法: ComposeOrchestrator._execute_task() 调用此方法
        将测试断言注入 Agent prompt，研究显示 pass@5 提升 20-30 点。
        """
        parts: list[str] = []
        if self.signature:
            parts.append(f"**函数签名**: `{self.signature}`")
        if self.behavior:
            parts.append("**行为契约**:")
            for b in self.behavior:
                parts.append(f"  - {b}")
        if self.tests:
            parts.append("**验收测试——以下断言必须全部通过**:")
            for t in self.tests:
                parts.append(f"  - {t}")
        if not parts:
            return ""
        return "## 验收标准\n\n" + "\n".join(parts)
