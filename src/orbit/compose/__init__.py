"""Compose 流水线——spec-driven 多 Agent 编排框架。

对标 MiMo Code compose/.bundle/ 15 技能。
核心: SKILL.md 技能文件 → ComposeParser 加载 → ComposeOrchestrator 编排执行。
"""

from orbit.compose.models import Skill, Spec, Task
from orbit.compose.orchestrator import ComposeOrchestrator
from orbit.compose.parser import ComposeParser

__all__ = [
    "ComposeOrchestrator",
    "ComposeParser",
    "Skill",
    "Spec",
    "Task",
]
