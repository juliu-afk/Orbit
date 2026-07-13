"""Orbit Skill 系统——通用 Skill 注册、匹配、热更新。

提供：
- SkillRegistry: 扫描 SKILL.md 文件、精确匹配、自然语言模糊匹配
- ChatSkill 模型: 聊天框可调用的 Skill 定义
- SkillWatcher: 文件系统 watcher → 热更新
"""

from orbit.skills.models import ChatMode, ChatSkill, SkillMatchResult, SkillVersion
from orbit.skills.registry import SkillRegistry
from orbit.skills.watcher import SkillWatcher

__all__ = [
    "ChatMode",
    "ChatSkill",
    "SkillMatchResult",
    "SkillVersion",
    "SkillRegistry",
    "SkillWatcher",
]
