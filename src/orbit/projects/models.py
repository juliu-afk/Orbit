"""项目注册表数据模型 (NL交互 PR #1).

ProjectRecord: 项目元数据 (名称/repo/Issue追踪器/文档源)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectRecord:
    """项目记录——存储项目元数据。"""

    name: str  # 项目名称 (唯一)
    local_path: str = ""  # 项目文件夹绝对路径 (Session PR #1)
    repo_url: str = ""  # Git 仓库 URL
    description: str = ""  # 项目描述 (用于关键词匹配)
    issue_tracker: str = ""  # github | jira | linear | tapd | ""
    issue_tracker_config: dict[str, str] = field(default_factory=dict)
    # { "owner": "juliu-afk", "repo": "Orbit", "api_token_env": "GITHUB_TOKEN" }
    doc_sources: list[str] = field(default_factory=list)  # 文档来源路径
    tags: list[str] = field(default_factory=list)  # 标签 (用于匹配)
    is_active: bool = True  # 是否活跃
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "local_path": self.local_path,
            "repo_url": self.repo_url,
            "description": self.description,
            "issue_tracker": self.issue_tracker,
            "issue_tracker_config": self.issue_tracker_config,
            "doc_sources": self.doc_sources,
            "tags": self.tags,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
