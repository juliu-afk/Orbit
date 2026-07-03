"""工具注册中心 (Step 5.5 PR #2 + Phase 1 升级).

权限隔离 + 滑动窗口限流 + 版本管理 + AST自注册 + JSON Schema + 并发安全.
"""

from orbit.tools.mcp_client import MCPClientConnection, MCPClientError
from orbit.tools.models import ToolInvocation, ToolPermission, ToolSchema
from orbit.tools.registry import (
    DoomLoopError,
    PermissionError,
    RateLimitError,
    ToolCall,
    ToolDeprecatedError,
    ToolEntry,
    ToolNotFoundError,
    ToolRegistry,
    WorkspaceViolationError,
    get_registry,
)

__all__ = [
    "ToolRegistry",
    "get_registry",
    "MCPClientConnection",
    "MCPClientError",
    "ToolEntry",
    "ToolCall",
    "ToolSchema",
    "ToolInvocation",
    "ToolPermission",
    "DoomLoopError",
    "PermissionError",
    "RateLimitError",
    "ToolDeprecatedError",
    "ToolNotFoundError",
    "WorkspaceViolationError",
]
