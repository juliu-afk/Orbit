"""工具注册中心——声明式工具注册 + 权限隔离 + 限流 + 版本管理。

拆分为 3 文件: models.py（异常+数据模型）、core.py（ToolRegistry 类）、__init__.py（re-export）。
"""

from orbit.tools.registry.models import (
    DoomLoopError,
    PermissionError,
    RateLimitError,
    ToolCall,
    ToolDeprecatedError,
    ToolEntry,
    ToolHandler,
    ToolNotFoundError,
    WorkspaceViolationError,
)
from orbit.tools.registry.core import ToolRegistry, _path_to_module, _version_key, get_registry

__all__ = [
    "DoomLoopError",
    "PermissionError",
    "RateLimitError",
    "ToolCall",
    "ToolDeprecatedError",
    "ToolEntry",
    "ToolHandler",
    "ToolNotFoundError",
    "ToolRegistry",
    "WorkspaceViolationError",
    "_path_to_module",
    "_version_key",
    "get_registry",
]
