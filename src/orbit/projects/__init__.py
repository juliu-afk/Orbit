"""NL交互 PR #1——项目注册表。

管理项目元数据: 名称/仓库/Issue追踪器/标签。
"""

from orbit.projects.models import ProjectRecord
from orbit.projects.registry import ProjectRegistry

__all__ = ["ProjectRecord", "ProjectRegistry"]
