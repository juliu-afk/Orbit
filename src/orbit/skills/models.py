"""Skill 系统数据模型。

ChatSkill: 聊天框可直接调用的 Skill 定义（兼容 compose Skill 的 SKILL.md 格式）
ChatMode: 四级权限模式——对标 Claude Code for VS Code
SkillMatchResult: 自然语言匹配结果（含置信度）
SkillVersion: 版本历史条目
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChatMode(StrEnum):
    """四级权限模式——对标 Claude Code for VS Code。

    MANUAL: 每次工具调用弹确认（读+写都确认）
    EDIT_AUTO: 读放行，写首次确认+会话记住
    PLAN: 只读分析+方案输出，拒绝所有写入
    AUTO: 全自动，不弹确认
    """

    MANUAL = "Manual"
    EDIT_AUTO = "Edit Automatically"
    PLAN = "Plan"
    AUTO = "Auto Mode"


class SkillTriggerType(StrEnum):
    """Skill 触发方式——决定路由优先级。"""

    SLASH = "slash"       # /xxx 精确命令匹配（最高优先级）
    NATURAL = "natural"   # 自然语言模糊匹配
    CHAIN = "chain"       # 编排链中的一环


class SkillVersion(BaseModel):
    """版本历史条目——每次 Skill 更新追加一条。"""

    version: str                                    # "1.2.0"
    changed_at: str = ""                            # ISO 8601 时间戳
    changed_by: str = "user"                        # "user" | "system"
    diff_summary: str = ""                          # 简短变更说明（≤100 字符）
    file_hash: str = ""                             # SHA256——用于回滚定位文件内容


class ChatSkill(BaseModel):
    """聊天框可调用的 Skill 定义。

    兼容 compose Skill 的 SKILL.md YAML frontmatter 格式，
    额外增加聊天框触发条件字段。
    """

    name: str = Field(..., description="Skill 唯一标识，如 'code-review'")
    description: str = Field("", description="一句话描述——用于自动匹配和列表展示")
    triggers: list[str] = Field(
        default_factory=list,
        description="自然语言触发词，如 ['审查', 'review', '检查代码']",
    )
    phase: str = Field(
        "chat",
        description="执行阶段: plan|implement|review|verify|merge|chat",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Skill 需要的工具列表，如 ['read_file', 'grep', 'glob']",
    )
    agent_role: str = Field("developer", description="执行 Agent 角色")
    body: str = Field("", description="Markdown body——Skill 指令 prompt")
    version: str = Field("1.0.0", description="语义化版本")
    is_chat_skill: bool = Field(
        True,
        description="True=聊天框可调用（/ 补全 + 自然语言匹配）",
    )
    is_chainable: bool = Field(
        False,
        description="True=可作为 ComposeOrchestrator 编排链的一环",
    )
    path: str = Field("", description="SKILL.md 文件路径（加载时填充）")


class SkillMatchResult(BaseModel):
    """自然语言匹配结果——置信度 + 匹配理由。"""

    skill: ChatSkill
    confidence: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="匹配置信度: ≥0.7 直接触发, 0.4-0.7 提示确认, <0.4 跳过",
    )
    trigger_type: SkillTriggerType = SkillTriggerType.NATURAL
    matched_by: str = Field("", description="匹配到的触发词或理由——调试用")
