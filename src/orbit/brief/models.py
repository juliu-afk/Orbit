"""项目说明书 + 基础代码包 + 边界规则 数据结构。

WHY dataclass 而非 Pydantic: 这些是内部数据对象，不经过 API 序列化。
保持与 projects/models.py 一致的 dataclass 风格。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BriefSection:
    """说明书的一个段落。

    WHY 独立 dataclass: 方便按标题索引和验证必填段落。
    """

    title: str  # "摘要" | "技术栈" | "命令" | "目录结构" | "代码风格" | "边界"
    content: str


# 6 个必填段落标题
REQUIRED_SECTIONS = ["摘要", "技术栈", "命令", "目录结构", "代码风格", "边界"]


@dataclass
class BriefRecord:
    """完整的项目说明书。

    对应 .orbit/brief.md 文件内容。
    """

    project_name: str
    sections: list[BriefSection] = field(default_factory=list)
    generated_at: float = 0.0  # unix timestamp
    generated_by: str = ""  # 模型名，如 "openai/glm-5.2"
    project_language: str = ""
    project_framework: str = ""

    def get_section(self, title: str) -> BriefSection | None:
        """按标题检索段落。"""
        for s in self.sections:
            if s.title == title:
                return s
        return None

    def is_valid(self) -> bool:
        """验证 6 个必填段落是否齐全。"""
        titles = {s.title for s in self.sections}
        return all(req in titles for req in REQUIRED_SECTIONS)

    def to_markdown(self) -> str:
        """序列化为 .orbit/brief.md 格式。"""
        lines = [f"# Project Brief: {self.project_name}\n"]
        for i, section in enumerate(self.sections, 1):
            lines.append(f"## {i}. {section.title}")
            lines.append(section.content.strip())
            lines.append("")
        lines.append(
            f"<!-- generated_at: {self.generated_at}, "
            f"generated_by: {self.generated_by}, "
            f"language: {self.project_language}, "
            f"framework: {self.project_framework} -->"
        )
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, markdown: str, project_name: str = "") -> "BriefRecord":
        """从 .orbit/brief.md 反序列化。

        WHY 类方法: 替代 __init__，与 to_markdown() 对称。
        """
        sections: list[BriefSection] = []
        current_title = ""
        current_lines: list[str] = []

        for line in markdown.split("\n"):
            stripped = line.strip()
            # 跳过 HTML 注释行
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue
            # 匹配 "## N. 标题" 格式
            if stripped.startswith("## ") and ". " in stripped:
                # 保存前一个段落
                if current_title:
                    sections.append(
                        BriefSection(title=current_title, content="\n".join(current_lines).strip())
                    )
                # 提取新标题——去掉 "## N. " 前缀
                header = stripped[3:]  # 去掉 "## "
                dot_pos = header.find(". ")
                current_title = header[dot_pos + 2 :] if dot_pos >= 0 else header
                current_lines = []
            elif current_title:
                current_lines.append(line)

        # 最后一个段落
        if current_title:
            sections.append(
                BriefSection(title=current_title, content="\n".join(current_lines).strip())
            )

        return cls(project_name=project_name, sections=sections)


@dataclass
class BasePackage:
    """基础代码包元数据——D:\\OrbitBasePackages\\index.json 中每条记录。"""

    id: str  # 唯一标识，如 "python-fastapi-minimal"
    language: str  # python | typescript | rust | go | ...
    framework: str = ""  # fastapi | react | actix | ...
    features: list[str] = field(default_factory=list)  # ["async", "pydantic", "sqlalchemy"]
    description: str = ""  # 一句话描述
    file_count: int = 0  # 模板文件数
    estimated_tokens: int = 0  # 预估 token 消耗
    cookiecutter_compat: bool = False  # 是否兼容 Cookiecutter 格式
    path: str = ""  # 库内相对路径

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "language": self.language,
            "framework": self.framework,
            "features": self.features,
            "description": self.description,
            "file_count": self.file_count,
            "estimated_tokens": self.estimated_tokens,
            "cookiecutter_compat": self.cookiecutter_compat,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BasePackage":
        return cls(
            id=data.get("id", ""),
            language=data.get("language", ""),
            framework=data.get("framework", ""),
            features=data.get("features", []),
            description=data.get("description", ""),
            file_count=data.get("file_count", 0),
            estimated_tokens=data.get("estimated_tokens", 0),
            cookiecutter_compat=data.get("cookiecutter_compat", False),
            path=data.get("path", ""),
        )


@dataclass
class PackageDecision:
    """LLM 对基础代码包注入的决策结果。

    WHY 独立类型: 决策本身需要被审计和缓存，不是 LLMResponse 的副产品。
    """

    decision: str  # "full" | "skeleton" | "skip"
    package_ids: list[str] = field(default_factory=list)  # 选中的包 ID
    reason: str = ""  # LLM 给出的理由


@dataclass
class BriefStatus:
    """项目说明书就绪状态——checker 模块的返回值。"""

    has_brief: bool = False
    has_base_package: bool = False
    has_boundaries: bool = False
    has_context_md: bool = False  # 目录级 context.md
    brief_path: str = ""
    base_path: str = ""
    boundaries_path: str = ""


@dataclass
class BoundaryRule:
    """单条边界规则——.orbit/boundaries/rules.yaml 中的一条。"""

    rule_id: str  # "no-float-money"
    description: str  # "金额一律用 Decimal，禁止 float/double"
    severity: str = "error"  # error | warning
    category: str = ""  # finance | security | governance | style
    enforcement: dict = field(default_factory=dict)
    # enforcement 子字段:
    #   static_analysis: dict  # ruff_rules, bandit_rules, grep_pattern
    #   pre_commit: bool
    #   review_checklist: bool
    #   runtime_assert: bool


@dataclass
class ProjectAnalysis:
    """CodeGraph 对项目代码库的分析结果——供 BriefGenerator 使用。

    WHY 独立 dataclass: 解耦 CodeGraph 输出与生成器输入，
    方便在不连 CodeGraph 时构造 mock。
    """

    language: str = ""  # 检测到的编程语言
    framework: str = ""  # 推测的框架
    directory_tree: str = ""  # 目录结构文本表示
    file_count: int = 0
    python_files: int = 0
    ts_files: int = 0
    js_files: int = 0
    other_files: int = 0
    key_files: list[str] = field(default_factory=list)  # 关键文件路径列表
    dependencies: list[str] = field(default_factory=list)  # 检测到的依赖
