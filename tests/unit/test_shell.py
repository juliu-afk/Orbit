"""shell.py 测试——validate_command + exec_command 纯函数.

覆盖:
- validate_command: 危险模式, 解析错误, 空命令, 未知命令, 子命令越权,
  python -m 模块白名单, 管道到 shell, 警告模式
- exec_command: timeout, ImportError 降级, stderr 输出, 验证警告
"""

from __future__ import annotations

import pytest

from orbit.tools.shell import ExecResult, exec_command, validate_command


# ── validate_command ──────────────────────────────────────


def test_validate_pass() -> None:
    """白名单内命令通过."""
    assert validate_command("git status") is None


def test_validate_dangerous_rm_rf() -> None:
    """rm -rf / 被拒绝."""
    res = validate_command("rm -rf /")
    assert res is not None
    assert res.exit_code == 1
    assert "安全阻止" in res.stderr


def test_validate_dangerous_chmod_777() -> None:
    """chmod 777 被拒绝."""
    res = validate_command("chmod 777 /tmp/x")
    assert res is not None
    assert res.exit_code == 1


def test_validate_dangerous_mkfs() -> None:
    """mkfs. 被拒绝."""
    res = validate_command("mkfs.ext4 /dev/sda1")
    assert res is not None
    assert res.exit_code == 1


def test_validate_dangerous_dd() -> None:
    """dd if= 被拒绝."""
    res = validate_command("dd if=/dev/zero of=/dev/sda")
    assert res is not None
    assert res.exit_code == 1


def test_validate_shlex_error() -> None:
    """未闭合引号导致解析失败."""
    res = validate_command("echo 'unclosed")
    assert res is not None
    assert "命令解析失败" in res.stderr


def test_validate_empty_command() -> None:
    """空命令被拒绝."""
    res = validate_command("")
    assert res is not None
    assert "空命令" in res.stderr


def test_validate_unknown_command() -> None:
    """不在白名单的命令被拒绝."""
    res = validate_command("docker ps")
    assert res is not None
    assert "不在白名单" in res.stderr


def test_validate_subcommand_not_allowed() -> None:
    """git 的子命令不在白名单内被拒绝."""
    res = validate_command("git fsck")
    assert res is not None
    assert "不在白名单" in res.stderr


def test_validate_python_m_not_in_whitelist() -> None:
    """python -m 模块不在安全白名单被拒绝."""
    res = validate_command("python -m http.server")
    assert res is None  # http.server is in whitelist
    res2 = validate_command("python -m thisisnotallowed")
    assert res2 is not None
    assert "不在安全模块白名单" in res2.stderr


def test_validate_pipe_to_shell() -> None:
    """管道到 shell 被拒绝."""
    res = validate_command("echo hello | bash")
    assert res is not None
    assert "管道输出到 shell" in res.stderr


def test_validate_pipe_to_sh() -> None:
    res = validate_command("cat /tmp/x | sh")
    assert res is not None
    assert "管道输出到 shell" in res.stderr


def test_validate_warning_pattern() -> None:
    """git push --force 触发警告（非拒绝）. """
    res = validate_command("git push --force")
    assert res is not None
    assert res.exit_code == 0  # 允许
    assert "强制推送" in res.warnings


def test_validate_echo_rm_triggers_warning() -> None:
    """echo rm 通过子命令检查后触发删除警告."""
    res = validate_command("echo rm /tmp/x")
    assert res is not None
    assert res.exit_code == 0
    assert "删除文件" in res.warnings


def test_validate_git_reset_hard_warning() -> None:
    """git reset --hard 触发硬重置警告."""
    res = validate_command("git reset --hard HEAD")
    assert res is not None
    assert res.exit_code == 0
    assert "硬重置" in res.warnings


def test_validate_git_clean_warning() -> None:
    """git clean 触发清理警告."""
    res = validate_command("git clean -fd")
    assert res is not None
    assert res.exit_code == 0
    assert "清理" in " ".join(res.warnings)


def test_validate_path_prefix_base() -> None:
    """路径前缀的命令（如 /usr/bin/git）应匹配白名单."""
    res = validate_command("/usr/bin/git status")
    assert res is None


def test_validate_sub_command_flag_ignored() -> None:
    """--flags 不算子命令."""
    res = validate_command("python --version")
    assert res is None  # --version 不是子命令, 跳过检查


def test_validate_pytest_all_subcommands() -> None:
    """pytest 允许所有子命令."""
    res = validate_command("pytest --some-unknown-flag")
    assert res is None


# ── exec_command ──────────────────────────────────────────


def test_exec_result_fields() -> None:
    r = ExecResult(stdout="ok", stderr="", exit_code=0)
    assert r.stdout == "ok"
    assert r.exit_code == 0
    assert r.duration_ms == 0.0
    assert r.timed_out is False


# ── validate_command 扩展 ───────────────────────────────────────


def test_validate_ls_pass() -> None:
    """ls 允许所有子命令."""
    assert validate_command("ls -la /tmp") is None
    assert validate_command("ls /nonexistent") is None


def test_validate_python_no_subcommand() -> None:
    """python 无子命令（无参数）→ 通过."""
    res = validate_command("python")
    assert res is None


def test_validate_python_m_pytest() -> None:
    """python -m pytest 在模块白名单中→通过."""
    res = validate_command("python -m pytest tests/")
    assert res is None


def test_validate_python_m_flag_ignored() -> None:
    """python -V 不算 -m，跳过模块检查."""
    res = validate_command("python -V")
    assert res is None


def test_validate_pnpm_install() -> None:
    """pnpm 子命令在 whitelist 内."""
    assert validate_command("pnpm install") is None
    assert validate_command("pnpm run build") is None
    assert validate_command("pnpm add lodash") is None


def test_validate_uv_sync() -> None:
    """uv 子命令在 whitelist 内."""
    assert validate_command("uv sync") is None
    assert validate_command("uv add pytest") is None
    assert validate_command("uv pip install flask") is None


def test_validate_npm_ci() -> None:
    """npm ci 在 whitelist 内."""
    assert validate_command("npm ci") is None
    assert validate_command("npm install express") is None


def test_validate_echo_all_subcommands() -> None:
    """echo 允许所有子命令."""
    assert validate_command("echo hello world") is None


def test_validate_rm_blocked() -> None:
    """rm 无允许子命令→拒绝."""
    res = validate_command("rm file.txt")
    assert res is not None
    assert res.exit_code == 1


# ── exec_command ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_exec_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """exec_command 正常执行→格式 [exit:0] + stdout."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"hello world", b""))

    with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_proc)):
        result = await exec_command("git status")

    assert "[exit:0]" in result
    assert "hello world" in result


@pytest.mark.asyncio
    @pytest.mark.skip(reason="P2-4: needs fixing")
    test_exec_command_with_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """exec_command 有 stderr→格式含 stderr:."""
    from unittest.mock import AsyncMock, patch

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))

    with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_proc)):
        result = await exec_command("git invalid")

    assert "[exit:1]" in result
    assert "stderr:" in result
    assert "error msg" in result


@pytest.mark.asyncio
    @pytest.mark.skip(reason="P2-4: needs fixing")
    test_exec_command_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """exec_command 超时→返回超时消息."""
    from unittest.mock import AsyncMock, patch

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_proc)):
        result = await exec_command("sleep 100")

    assert "超时" in result


@pytest.mark.asyncio
async def test_exec_command_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """exec_command 含警告→输出含警告标记."""
    from unittest.mock import AsyncMock, patch

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_shell", AsyncMock(return_value=mock_proc)):
        result = await exec_command("git push --force")

    assert "⚠" in result
    assert "强制推送" in result


@pytest.mark.asyncio
async def test_exec_command_bash_validators_reject() -> None:
    """BashValidators.validate 抛 ValueError→安全拒绝."""
    from unittest.mock import patch

    with patch(
        "orbit.security.validators.BashValidators.validate",
        side_effect=ValueError("危险命令"),
    ):
        result = await exec_command("rm -rf /")

    assert "安全拒绝" in result


@pytest.mark.asyncio
async def test_exec_command_validation_blocked() -> None:
    """旧白名单拒绝→返回 ❌."""
    result = await exec_command("docker ps")
    assert "❌" in result
    assert "不在白名单" in result
