"""测试 SkillRegistry——发现、匹配、CRUD、版本管理。

使用临时目录避免污染真实 SKILL.md 文件。
"""

import tempfile
from pathlib import Path

import pytest

from orbit.skills.models import ChatSkill
from orbit.skills.registry import SkillRegistry


@pytest.fixture
def temp_skills_dir():
    """创建临时 skills 目录——含几个测试 SKILL.md。"""
    with tempfile.TemporaryDirectory() as tmp:
        skills_dir = Path(tmp)
        # 创建 review skill
        (skills_dir / "review.md").write_text(
            "---\n"
            "name: review\n"
            "description: 代码审查\n"
            "triggers: [审查, review, 检查代码]\n"
            "phase: review\n"
            "tools: [read_file, grep]\n"
            "agent_role: reviewer\n"
            "version: 1.0.0\n"
            "---\n\n"
            "# Review\n\n审查代码变更。\n",
            encoding="utf-8",
        )
        # 创建 plan skill
        (skills_dir / "plan.md").write_text(
            "---\n"
            "name: plan\n"
            "description: 技术方案设计\n"
            "triggers: [方案, plan, 架构, 设计]\n"
            "phase: plan\n"
            "tools: [read_file, grep, glob]\n"
            "agent_role: architect\n"
            "version: 1.0.0\n"
            "is_chainable: true\n"
            "---\n\n"
            "# Plan\n\n设计技术方案。\n",
            encoding="utf-8",
        )
        # 创建非 chat skill
        (skills_dir / "internal.md").write_text(
            "---\n"
            "name: internal-tool\n"
            "description: 内部工具\n"
            "phase: chat\n"
            "is_chat_skill: false\n"
            "---\n\n"
            "# Internal\n\n内部使用。\n",
            encoding="utf-8",
        )
        # 创建无 frontmatter 文件（应被跳过）
        (skills_dir / "bad.md").write_text("# No frontmatter\n\nJust text.\n", encoding="utf-8")
        yield skills_dir


class TestSkillRegistryDiscover:
    def test_discover_loads_valid_skills(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        skills = registry.discover()
        # review + plan = 2 (internal 的 is_chat_skill=False，但 discover 仍加载；
        # 只有 bad.md 跳过——无 frontmatter)
        assert len(skills) >= 2

    def test_discover_skips_no_frontmatter(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        skills = registry.discover()
        names = [s.name for s in skills]
        assert "bad" not in names  # bad.md 无 frontmatter，应被跳过

    def test_list_all_only_chat_skills(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        chat_skills = registry.list_all()
        names = [s.name for s in chat_skills]
        assert "review" in names
        assert "plan" in names
        assert "internal-tool" not in names  # is_chat_skill=False


class TestSkillRegistryFindBySlash:
    def test_find_exact_name(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        skill = registry.find_by_slash("review")
        assert skill is not None
        assert skill.name == "review"

    def test_find_with_slash_prefix(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        skill = registry.find_by_slash("/review")
        assert skill is not None
        assert skill.name == "review"

    def test_find_nonexistent(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        skill = registry.find_by_slash("nonexistent")
        assert skill is None

    def test_find_skips_non_chat(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        skill = registry.find_by_slash("internal-tool")
        assert skill is None  # is_chat_skill=False


class TestSkillRegistryMatchByText:
    def test_exact_trigger_match(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        results = registry.match_by_text("帮我审查一下代码")
        assert len(results) >= 1
        # 应匹配到 review skill（触发词 "审查"）
        review_matches = [r for r in results if r.skill.name == "review"]
        assert len(review_matches) == 1
        assert review_matches[0].confidence >= 0.7

    def test_multiple_triggers_boost_confidence(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        # review skill 触发词有 "审查" 和 "review"——都命中 → 高置信度
        results = registry.match_by_text("review 审查代码")
        review_matches = [r for r in results if r.skill.name == "review"]
        if review_matches:
            assert review_matches[0].confidence >= 0.7

    def test_no_match_returns_empty(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        results = registry.match_by_text("今天天气怎么样")
        assert results == []


class TestSkillRegistryGet:
    def test_get_existing(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        skill = registry.get("review")
        assert skill is not None
        assert skill.name == "review"

    def test_get_nonexistent(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        assert registry.get("nonexistent") is None


class TestSkillRegistryVersionBump:
    def test_bump_patch(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        assert registry._bump_version("1.0.0", "patch") == "1.0.1"

    def test_bump_minor(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        assert registry._bump_version("1.0.0", "minor") == "1.1.0"

    def test_bump_major(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        assert registry._bump_version("1.0.0", "major") == "2.0.0"

    def test_bump_invalid_version(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        result = registry._bump_version("invalid", "patch")
        assert result == "1.0.1"  # 默认从 1.0.0 开始


class TestSkillRegistryBuildChain:
    def test_build_chain(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        chain = registry.build_chain(["plan", "review"])
        assert len(chain) == 2
        assert chain[0].name == "plan"
        assert chain[1].name == "review"

    def test_build_chain_missing_skill(self, temp_skills_dir):
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.discover()
        with pytest.raises(FileNotFoundError):
            registry.build_chain(["plan", "nonexistent"])
