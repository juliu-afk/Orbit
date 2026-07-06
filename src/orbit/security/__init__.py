"""安全权限模块——5层 deny-wins 权限引擎。

对标 Claude Code 7-layer permission + OpenClaw 9-layer policy merge。
Orbit 简化为 5 层: agent_role → tool_category → path_scope → sandbox → global_deny。
"""

from orbit.security.constants import SENSITIVE_FILE_GLOB, SENSITIVE_FILE_NAMES  # noqa: F401
from orbit.security.guard import WorkspaceGuard
from orbit.security.models import PermissionLayer, SecurityPolicy
from orbit.security.permission import PermissionEngine
from orbit.security.validators import BashValidators

__all__ = [
    "BashValidators",
    "PermissionEngine",
    "PermissionLayer",
    "SENSITIVE_FILE_GLOB",
    "SENSITIVE_FILE_NAMES",
    "SecurityPolicy",
    "WorkspaceGuard",
]
