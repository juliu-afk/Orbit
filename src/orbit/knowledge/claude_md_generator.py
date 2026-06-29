"""CLAUDE.md 自动生成——业务层减熵 P2.

从六图谱扫描生成项目说明书，Agent 新建项目时自动产出初始 CLAUDE.md.
"""

from __future__ import annotations

from typing import Any


class ClaudeMdGenerator:
    """六图谱 → CLAUDE.md 项目说明书.

    用法:
        gen = ClaudeMdGenerator(graph_manager=manager)
        content = await gen.generate()
        # → 完整的 CLAUDE.md markdown 内容
    """

    SECTIONS = [
        "项目名称与概述",
        "技术栈",
        "项目结构",
        "术语定义",
        "实现约束",
        "编码约定",
        "测试框架",
        "行为拦截清单",
    ]

    def __init__(self, graph_manager: Any) -> None:
        self._graphs = graph_manager

    async def generate(self) -> str:
        sections: dict[str, str] = {}

        sections["项目名称与概述"] = await self._extract_overview()
        sections["技术栈"] = await self._extract_tech_stack()
        sections["项目结构"] = await self._extract_structure()
        sections["术语定义"] = await self._extract_terminology()
        sections["实现约束"] = self._extract_constraints()
        sections["编码约定"] = self._extract_coding_conventions()
        sections["测试框架"] = await self._extract_test_framework()
        sections["行为拦截清单"] = self._extract_intercept_rules()

        return self._assemble(sections)

    # ── 提取方法 ───────────────────────────────────────

    async def _extract_overview(self) -> str:
        """项目概述——从 pyproject.toml/package.json 提取."""
        parts = ["# 项目概述", ""]
        try:
            config = self._graphs.config
            name = config.get("name", "Unknown")
            desc = config.get("description", "")
            parts.append(f"> {desc}")
            parts.append(f"**项目名称**: {name}")
        except Exception:
            parts.append("> 自动生成的项目说明书")
        return "\n".join(parts)

    async def _extract_tech_stack(self) -> str:
        """技术栈——从配置图谱提取."""
        parts = ["## 技术栈", ""]
        try:
            config = self._graphs.config
            deps = config.get("dependencies", {})
            if deps:
                parts.append("| 层级 | 组件 |")
                parts.append("|------|------|")
                for category, packages in deps.items():
                    parts.append(f"| {category} | {', '.join(packages)} |")
        except Exception:
            parts.append("（从 pyproject.toml/package.json 自动提取）")
        return "\n".join(parts)

    async def _extract_structure(self) -> str:
        """项目结构——从代码图谱提取目录树."""
        parts = ["## 项目结构", "", "```"]
        try:
            code = self._graphs.code
            tree = code.get_directory_tree() if code else {}
            parts.append(tree.get("text", "（从代码图谱提取）"))
        except Exception:
            parts.append("（从代码图谱自动提取）")
        parts.append("```")
        return "\n".join(parts)

    async def _extract_terminology(self) -> str:
        """术语——从知识图谱提取核心概念."""
        parts = ["## 术语定义", ""]
        try:
            knowledge = self._graphs.knowledge
            concepts = knowledge.list_concepts() if knowledge else []
            for c in concepts[:10]:
                parts.append(f"- **{c.get('name')}**: {c.get('description', '')}")
        except Exception:
            parts.append("（从知识图谱自动提取）")
        return "\n".join(parts)

    def _extract_constraints(self) -> str:
        return "## 实现约束\n\n（从代码模式和配置扫描提取）"

    def _extract_coding_conventions(self) -> str:
        return "## 编码约定\n\n（从代码风格分析提取）"

    async def _extract_test_framework(self) -> str:
        parts = ["## 测试框架", ""]
        try:
            config = self._graphs.config
            test_deps = config.get("test_dependencies", ["pytest"])
            parts.append(f"- 测试框架: {', '.join(test_deps)}")
        except Exception:
            parts.append("- pytest（默认）")
        return "\n".join(parts)

    def _extract_intercept_rules(self) -> str:
        return "## 行为拦截清单\n\n（从项目规则提取）"

    def _assemble(self, sections: dict[str, str]) -> str:
        """组装为完整 CLAUDE.md."""
        lines = [
            sections["项目名称与概述"],
            "",
            sections["技术栈"],
            "",
            sections["项目结构"],
            "",
            sections["术语定义"],
            "",
            sections["实现约束"],
            "",
            sections["编码约定"],
            "",
            sections["测试框架"],
            "",
            sections["行为拦截清单"],
        ]
        return "\n".join(lines)
