"""ComposeParser——SKILL.md 自发现 + Spec 解析。

对标 MiMo Code compose/.bundle/ 15 技能的 SKILL.md 格式。
AST 自发现模式——对标 Hermes discover_builtin_tools()。

SKILL.md 格式:
    ---
    name: compose:plan
    description: 写 specs-driven 实现方案
    phase: plan
    tools: [read_file, grep, glob]
    agent_role: architect
    ---
    # compose:plan

    ## 流程
    1. 读取 spec 文件...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

from orbit.compose.models import Skill, SkillPhase

if TYPE_CHECKING:
    from orbit.compose.models import Spec

logger = structlog.get_logger()

# SKILL.md 所在目录
SKILLS_DIR = Path(__file__).parent / "skills"

# YAML frontmatter 正则: ---\n...\n---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class ComposeParser:
    """SKILL.md 加载器 + Spec 解析器。

    Usage:
        parser = ComposeParser()
        skills = parser.discover_skills()  # AST 自发现
        skill = parser.load_skill("compose:plan")  # 按名称加载
        spec = parser.parse_spec(spec_text)  # 解析 spec YAML
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._skills_dir = skills_dir or SKILLS_DIR
        self._cache: dict[str, Skill] = {}

    def discover_skills(self) -> list[Skill]:
        """AST 自发现——扫描 skills/ 目录下所有 .md 文件。

        对标 Hermes discover_builtin_tools():
        - 扫描目录 → 解析 YAML frontmatter → Skill 对象
        - 缓存结果以避免重复解析
        """
        if self._cache:
            return list(self._cache.values())

        if not self._skills_dir.exists():
            logger.warning("skills_dir_not_found", path=str(self._skills_dir))
            return []

        skills = []
        for md_file in sorted(self._skills_dir.glob("*.md")):
            try:
                skill = self._load_skill_file(md_file)
                if skill:
                    skills.append(skill)
                    self._cache[skill.name] = skill
            except (OSError, UnicodeDecodeError, ValueError) as e:
                # OSError: 文件读取失败
                # UnicodeDecodeError: 编码错误
                # ValueError: YAML frontmatter 解析失败
                logger.warning("skill_load_failed", file=str(md_file), error=str(e), exc_info=True)

        logger.info("skills_discovered", count=len(skills))
        return skills

    def load_skill(self, name: str) -> Skill | None:
        """按名称加载技能——先发现所有技能，再从缓存取。"""
        if not self._cache:
            self.discover_skills()
        return self._cache.get(name)

    def parse_spec(self, spec_text: str) -> Spec:
        """解析 spec YAML 文本 → Spec 模型。

        spec 格式:
            title: "项目名称"
            description: "项目描述"
            language: python
            constraints:
              - "使用 pytest"
            tasks:
              - id: "task-1"
                description: "写测试"
                agent_role: "developer"
                skill: "compose:tdd"
        """
        from orbit.compose.models import Spec, Task

        data = yaml.safe_load(spec_text)
        if not isinstance(data, dict):
            raise ValueError("spec 必须是 YAML dict")

        tasks_raw = data.get("tasks", [])
        tasks = [
            Task(
                id=t.get("id", f"task-{i}"),
                description=t.get("description", ""),
                agent_role=t.get("agent_role", "developer"),
                skill=t.get("skill", ""),
                depends_on=t.get("depends_on", []),
            )
            for i, t in enumerate(tasks_raw)
        ]

        return Spec(
            title=data.get("title", "Untitled"),
            description=data.get("description", ""),
            tasks=tasks,
            language=data.get("language", "python"),
            constraints=data.get("constraints", []),
        )

    # ── 内部 ─────────────────────────────────────

    def _load_skill_file(self, md_file: Path) -> Skill | None:
        """加载单个 SKILL.md 文件——解析 YAML frontmatter + markdown body。"""
        content = md_file.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(content)
        if not match:
            logger.warning("skill_no_frontmatter", file=str(md_file))
            return None

        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return None

        body = content[match.end() :].strip()
        phase_raw = frontmatter.get("phase", "implement")

        return Skill(
            name=frontmatter.get("name", md_file.stem),
            description=frontmatter.get("description", ""),
            phase=(
                SkillPhase(phase_raw)
                if phase_raw in SkillPhase._value2member_map_
                else SkillPhase.IMPLEMENT
            ),
            tools=frontmatter.get("tools", []),
            agent_role=frontmatter.get("agent_role", "developer"),
            body=body,
            path=str(md_file),
        )
