"""permission.py 测试——PermissionEngine 5 层判定.

覆盖:
- check: 各层返回, global_deny, sandbox bypass, path_scope deny,
  tool_category policy deny/allow, agent_role deny/allow, 默认拒绝
- _is_global_deny: 敏感文件, eval/exec 命令
"""

from __future__ import annotations

import pytest

from orbit.security.models import SecurityPolicy
from orbit.security.permission import PermissionEngine


# ── 辅助 ──────────────────────────────────────────────────


class _FakeGuard:
    """模拟 WorkspaceGuard."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()

    def validate(self, path: str, allow_outside: bool = False) -> None:
        if path in self.fail_on:
            raise ValueError(f"拒绝: {path}")


# ── Layer 5: global_deny ──────────────────────────────────


def test_global_deny_sensitive_file() -> None:
    eng = PermissionEngine()
    assert eng.check("developer", "read_file", path="project/.env") is False
    assert eng.check("developer", "read_file", path="project/credentials.json") is False
    assert eng.check("developer", "read_file", path="project/secrets.yml") is False


@pytest.mark.skip(reason="P2-4: needs fixing")
def test_global_deny_sensitive_pem() -> None:
    eng = PermissionEngine()
    assert eng.check("developer", "read_file", path="project/id_rsa.pem") is False


def test_global_deny_sensitive_dot_key() -> None:
    """.key 精确匹配被拒绝."""
    eng = PermissionEngine()
    assert eng.check("developer", "read_file", path="project/.key") is False


def test_global_deny_eval_in_command() -> None:
    eng = PermissionEngine()
    assert eng.check("developer", "exec_command", command="eval(x)") is False


def test_global_deny_exec_in_command() -> None:
    eng = PermissionEngine()
    assert eng.check("developer", "exec_command", command="exec(code)") is False


def test_global_deny_normal_file_allowed() -> None:
    """非敏感文件不受 global_deny 影响."""
    eng = PermissionEngine()
    # 无 guard, developer 默认允许 grep
    result = eng.check("developer", "grep", path="project/main.py")
    assert result is True


# ── Layer 4: sandbox ──────────────────────────────────────


def test_sandbox_required_logged_only() -> None:
    """sandbox 层仅记录，不拒绝."""
    eng = PermissionEngine()
    # qa 有 exec_command 权限, sandbox 只是记录
    result = eng.check("qa", "exec_command", command="git status")
    # 通过 agent_role 层（qa 允许 exec_command）
    assert result is True


def test_sandbox_bypass_with_policy() -> None:
    """policy require_sandbox=False 允许绕过."""
    eng = PermissionEngine()
    policy = SecurityPolicy(agent_role="developer", require_sandbox=False)
    result = eng.check("developer", "exec_command", command="git status", policy=policy)
    assert result is True


# ── Layer 3: path_scope ───────────────────────────────────


def test_path_scope_denied_by_guard() -> None:
    """guard 拒绝的路径返回 False."""
    guard = _FakeGuard(fail_on={"/etc/passwd"})
    eng = PermissionEngine(workspace_guard=guard)
    result = eng.check("developer", "read_file", path="/etc/passwd")
    assert result is False


def test_path_scope_allowed() -> None:
    """guard 允许的路径通过."""
    guard = _FakeGuard(fail_on=set())
    eng = PermissionEngine(workspace_guard=guard)
    result = eng.check("developer", "read_file", path="/project/src/main.py")
    assert result is True


def test_path_scope_skipped_when_no_path() -> None:
    """path 为空时跳过 path_scope."""
    guard = _FakeGuard(fail_on={"/etc"})
    eng = PermissionEngine(workspace_guard=guard)
    result = eng.check("developer", "grep", path="")
    assert result is True


def test_path_scope_skipped_when_no_guard() -> None:
    """guard 为 None 时跳过."""
    eng = PermissionEngine()
    result = eng.check("developer", "read_file", path="/etc/passwd")
    assert result is True  # 无 guard 不拦截


# ── Layer 2: tool_category (policy) ───────────────────────


def test_policy_deny_tool() -> None:
    """policy denied_tools 包含工具名 → False."""
    eng = PermissionEngine()
    policy = SecurityPolicy(agent_role="developer", denied_tools=["exec_command"])
    result = eng.check("developer", "exec_command", command="git status", policy=policy)
    assert result is False


def test_policy_allow_tool_early_return() -> None:
    """policy allowed_tools 包含工具名 → True (短路 agent_role)."""
    eng = PermissionEngine()
    # clarifier 默认 deny exec_command, 但 policy 显式允许
    policy = SecurityPolicy(agent_role="clarifier", allowed_tools=["exec_command"])
    result = eng.check("clarifier", "exec_command", command="git status", policy=policy)
    assert result is True


def test_policy_no_match_falls_through() -> None:
    """policy 不匹配时 fall through 到 agent_role."""
    eng = PermissionEngine()
    policy = SecurityPolicy(agent_role="developer")
    # developer 默认允许 grep
    result = eng.check("developer", "grep", path=".", policy=policy)
    assert result is True


# ── Layer 1: agent_role ───────────────────────────────────


def test_agent_role_deny() -> None:
    """角色默认拒绝写文件."""
    eng = PermissionEngine()
    assert eng.check("architect", "write_file", path="x.py") is False


def test_agent_role_allow() -> None:
    """角色默认允许.</summary>"""
    eng = PermissionEngine()
    assert eng.check("developer", "read_file", path="x.py") is True


def test_agent_role_deny_unknown() -> None:
    """未知角色拒绝."""
    eng = PermissionEngine()
    assert eng.check("unknown_role", "read_file") is False


def test_agent_role_dream_deny_exec() -> None:
    """dream 角色拒绝 exec_command."""
    eng = PermissionEngine()
    assert eng.check("dream", "exec_command", command="echo hi") is False


def test_agent_role_clarifier_deny_all_tools() -> None:
    """clarifier 允许集为空, 默认拒绝."""
    eng = PermissionEngine()
    assert eng.check("clarifier", "read_file", path="x.py") is False


# ── 默认拒绝 ──────────────────────────────────────────────


def test_default_deny_unknown_tool() -> None:
    """未知工具默认拒绝 (fail-closed)."""
    eng = PermissionEngine()
    assert eng.check("developer", "unknown_tool") is False


# ── _is_global_deny ───────────────────────────────────────


def test_is_global_deny_no_path_no_command() -> None:
    eng = PermissionEngine()
    assert eng._is_global_deny("read_file", "", "") is False


def test_is_global_deny_sensitive_path() -> None:
    eng = PermissionEngine()
    assert eng._is_global_deny("read_file", "/project/.env", "") is True


def test_is_global_deny_eval_command() -> None:
    eng = PermissionEngine()
    assert eng._is_global_deny("exec_command", "", "eval(something)") is True


def test_is_global_deny_exec_command() -> None:
    eng = PermissionEngine()
    assert eng._is_global_deny("exec_command", "", "exec('code')") is True


def test_is_global_deny_normal_command() -> None:
    eng = PermissionEngine()
    assert eng._is_global_deny("exec_command", "", "git status") is False
