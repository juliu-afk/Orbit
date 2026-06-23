"""工具注册中心数据模型 (Step 5.5 PR #2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class ToolSchema:
    """工具元数据——声明式注册。

    allowed_agents: 白名单——只有列表中的 Agent 可调用此工具。
    rate_limit: 每分钟最大调用次数 (0=无限流)。
    cache_ttl: 结果缓存时间 (秒, 0=不缓存)。
    """

    name: str
    version: str  # semver: "1.0.0"
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    returns: dict[str, Any] = field(default_factory=dict)
    permissions: list[ToolPermission] = field(default_factory=list)
    allowed_agents: list[str] = field(default_factory=list)  # 白名单
    rate_limit: int = 0  # 每分钟上限, 0=无限
    timeout_seconds: int = 30
    is_async: bool = False
    cache_ttl: int = 0
    deprecated: bool = False
    deprecated_message: str = ""


@dataclass
class ToolInvocation:
    """工具调用记录。"""

    tool_name: str
    tool_version: str
    agent_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    status: str = "success"  # success | error | rate_limited | permission_denied
    duration_ms: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "agent_name": self.agent_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
