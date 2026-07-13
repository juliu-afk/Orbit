"""测试 ChatSkill / ChatMode / SkillMatchResult / SkillVersion 模型。"""

import pytest
from orbit.skills.models import (
    ChatMode,
    ChatSkill,
    SkillMatchResult,
    SkillVersion,
    SkillTriggerType,
)


class TestChatMode:
    def test_mode_values(self):
        assert ChatMode.MANUAL == "Manual"
        assert ChatMode.EDIT_AUTO == "Edit Automatically"
        assert ChatMode.PLAN == "Plan"
        assert ChatMode.AUTO == "Auto Mode"

    def test_parse_from_string(self):
        assert ChatMode("Manual") == ChatMode.MANUAL
        assert ChatMode("Plan") == ChatMode.PLAN
        assert ChatMode("Auto Mode") == ChatMode.AUTO

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            ChatMode("Invalid")


class TestChatSkill:
    def test_minimal_creation(self):
        skill = ChatSkill(name="test-skill", description="A test skill")
        assert skill.name == "test-skill"
        assert skill.is_chat_skill is True
        assert skill.is_chainable is False
        assert skill.version == "1.0.0"

    def test_full_creation(self):
        skill = ChatSkill(
            name="code-review",
            description="审查代码",
            triggers=["审查", "review"],
            phase="review",
            tools=["read_file", "grep"],
            agent_role="reviewer",
            body="# Review\n\nCheck code.",
            version="1.2.0",
            is_chat_skill=True,
            is_chainable=True,
        )
        assert skill.triggers == ["审查", "review"]
        assert skill.tools == ["read_file", "grep"]
        assert skill.agent_role == "reviewer"

    def test_defaults(self):
        skill = ChatSkill(name="test")
        assert skill.triggers == []
        assert skill.tools == []
        assert skill.body == ""
        assert skill.path == ""


class TestSkillMatchResult:
    def test_creation(self):
        skill = ChatSkill(name="review", triggers=["审查"])
        result = SkillMatchResult(
            skill=skill,
            confidence=0.85,
            trigger_type=SkillTriggerType.NATURAL,
            matched_by="审查",
        )
        assert result.confidence == 0.85
        assert result.trigger_type == SkillTriggerType.NATURAL

    def test_confidence_bounds(self):
        skill = ChatSkill(name="x")
        # ge=0.0
        with pytest.raises(Exception):
            SkillMatchResult(skill=skill, confidence=-0.1)
        # le=1.0
        with pytest.raises(Exception):
            SkillMatchResult(skill=skill, confidence=1.1)


class TestSkillVersion:
    def test_creation(self):
        v = SkillVersion(version="1.0.0", changed_at="2026-07-13", diff_summary="创建")
        assert v.version == "1.0.0"
        assert v.changed_by == "user"
