"""PermissionEngine——5层 deny-wins 权限判定引擎。

核心原则: "Explicit deny always wins; explicit allow overrides default deny."

层序（高→低优先级）:
  5. global_deny — 硬拒绝（.env, rm -rf /, eval()）
  4. sandbox — 写文件/shell 需经沙箱
  3. path_scope — workspace guard
  2. tool_category — 读写分类
  1. agent_role — 角色默认权限
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.observability.audit import AuditLogger
from orbit.security.models import PermissionLayer, SecurityPolicy

logger = structlog.get_logger("orbit.security")
_audit = AuditLogger(trace_id="permission-engine")


# 5C.2: 工具分类——READ vs WRITE 权限粒度
TOOL_CATEGORY_READ = {"read_file", "grep", "glob"}
TOOL_CATEGORY_WRITE = {"write_file", "edit_file", "exec_command"}

# 角色默认工具权限
_ROLE_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "architect": {
        "allow": ["read_file", "grep", "glob"],
        "deny": ["write_file", "edit_file", "exec_command"],
    },
    "developer": {
        "allow": ["read_file", "write_file", "edit_file", "grep", "glob", "exec_command"],
        "deny": [],
    },
    "reviewer": {"allow": ["read_file", "grep", "glob"], "deny": ["write_file", "edit_file"]},
    "qa": {"allow": ["read_file", "exec_command"], "deny": ["write_file", "edit_file"]},
    "config_manager": {"allow": ["read_file", "write_file"], "deny": ["exec_command"]},
    "clarifier": {"allow": [], "deny": ["write_file", "edit_file", "exec_command"]},
    "dream": {
        "allow": ["read_file", "write_file", "edit_file", "grep", "glob"],
        "deny": ["exec_command"],
    },
}


class PermissionEngine:
    """5 层 deny-wins 权限引擎。

    Usage:
        engine = PermissionEngine()
        engine.check("developer", "write_file", "/project/src/file.py")
    """

    def __init__(self, workspace_guard: Any = None) -> None:
        self._guard = workspace_guard  # WorkspaceGuard

    def check(
        self,
        agent_role: str,
        tool_name: str,
        path: str = "",
        command: str = "",
        policy: SecurityPolicy | None = None,
    ) -> bool:
        """逐层检查权限——任一层 deny → False。

        Returns:
            True = 允许执行
        """
        # Layer 5: global_deny（最高优先级）
        if self._is_global_deny(tool_name, path, command):
            logger.warning(
                "permission_denied",
                layer=PermissionLayer.GLOBAL_DENY.value,
                agent=agent_role,
                tool=tool_name,
            )
            _audit.log(
                "permission_engine",
                "deny_global",
                status="denied",
                agent=agent_role,
                tool=tool_name,
            )
            return False

        # Layer 4: sandbox（shell 必须隔离）
        # P1-3: 不仅记录，还拒绝——除非调用方显式绕过沙箱（仅测试用）
        if tool_name == "exec_command":
            if policy and not policy.require_sandbox:
                pass  # 显式绕过沙箱（仅限测试）
            else:
                # P1 SEC-2: sandbox 层 fail-closed——
                # 无沙箱保护的 exec_command 应拒绝而非依赖调用方自觉
                logger.warning(
                    "permission_denied",
                    layer="sandbox",
                    reason="exec_command 需要沙箱保护",
                    agent=agent_role,
                )
                return False

        # Layer 3: path_scope（workspace guard）
        if path and self._guard:
            try:
                allow_outside = tool_name in ("read_file", "grep", "glob")
                self._guard.validate(path, allow_outside=allow_outside)
            except ValueError:
                logger.warning(
                    "permission_denied",
                    layer=PermissionLayer.PATH_SCOPE.value,
                    agent=agent_role,
                    path=path,
                )
                _audit.log(
                    "permission_engine",
                    "deny_path_scope",
                    status="denied",
                    agent=agent_role,
                    path=path,
                )
                return False

        # Layer 2: tool_category（读写分类 + policy deny）
        if policy:
            if tool_name in policy.denied_tools:
                logger.warning(
                    "permission_denied",
                    layer=PermissionLayer.TOOL_CATEGORY.value,
                    agent=agent_role,
                    tool=tool_name,
                )
                _audit.log(
                    "permission_engine",
                    "deny_tool_category",
                    status="denied",
                    agent=agent_role,
                    tool=tool_name,
                )
                return False
            if tool_name in policy.allowed_tools:
                return True

        # Layer 1: agent_role（角色默认）
        defaults = _ROLE_DEFAULTS.get(agent_role, {})
        if tool_name in defaults.get("deny", []):
            logger.warning(
                "permission_denied",
                layer=PermissionLayer.AGENT_ROLE.value,
                agent=agent_role,
                tool=tool_name,
            )
            _audit.log(
                "permission_engine",
                "deny_agent_role",
                status="denied",
                agent=agent_role,
                tool=tool_name,
            )
            return False
        if tool_name in defaults.get("allow", []):
            _audit.log(
                "permission_engine",
                "allow_explicit",
                status="allowed",
                agent=agent_role,
                tool=tool_name,
            )
            return True

        # 无匹配——默认拒绝（P1 SEC-1: fail-closed——未知工具不应放行）
        logger.warning(
            "permission_denied",
            layer="default",
            agent=agent_role,
            tool=tool_name,
        )
        _audit.log(
            "permission_engine", "deny_default", status="denied",
            agent=agent_role, tool=tool_name,
            reason="no matching permission policy",
        )
        return False

    # ── 内部 ─────────────────────────────────────

    def _is_global_deny(self, tool_name: str, path: str, command: str) -> bool:
        """Layer 5: 全局硬拒绝检查。"""
        # 禁止访问敏感文件
        sensitive_patterns = [".env", ".pem", ".key", "credentials", "secrets"]
        fname = path.split("/")[-1] if path else ""
        for p in sensitive_patterns:
            if fname == p or fname.startswith(p):
                return True

        # 禁止 eval/exec
        return bool(command and ("eval(" in command or "exec(" in command))
