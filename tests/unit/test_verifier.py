"""ExecutorVerifier——验证命令白名单 + 纯函数单元测试."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.goal.verifier import (
    ALLOWED_VERIFICATION_COMMANDS,
    CommandNotAllowedError,
    ExecutorVerifier,
    VerificationResult,
)


class TestCommandNotAllowedError:
    def test_is_value_error(self):
        assert issubclass(CommandNotAllowedError, ValueError)


class TestAllowedVerificationCommands:
    def test_is_frozenset(self):
        assert isinstance(ALLOWED_VERIFICATION_COMMANDS, frozenset)

    def test_contains_common_tools(self):
        assert "pytest" in ALLOWED_VERIFICATION_COMMANDS
        assert "python" in ALLOWED_VERIFICATION_COMMANDS
        assert "npm" in ALLOWED_VERIFICATION_COMMANDS
        assert "ruff" in ALLOWED_VERIFICATION_COMMANDS


class TestVerificationResult:
    """VerificationResult dataclass——纯属性"""

    def test_empty(self):
        vr = VerificationResult()
        assert vr.all_passed is True
        assert vr.results == []
        assert vr.failed_commands == []
        assert vr.passed_count == 0
        assert vr.total_count == 0

    def test_mixed_results(self):
        vr = VerificationResult(all_passed=False, results=[
            {"command": "pytest", "passed": True, "exit_code": 0},
            {"command": "lint", "passed": False, "exit_code": 1},
        ])
        assert vr.all_passed is False
        assert vr.passed_count == 1
        assert vr.total_count == 2
        assert len(vr.failed_commands) == 1
        assert vr.failed_commands[0]["command"] == "lint"

    def test_to_prompt_section_empty(self):
        vr = VerificationResult(results=[])
        assert "（无验证命令）" in vr.to_prompt_section()

    def test_to_prompt_section_with_results(self):
        vr = VerificationResult(all_passed=False, results=[
            {"command": "pytest tests/", "passed": True, "exit_code": 0},
            {"command": "ruff check", "passed": False, "exit_code": 1, "stderr_tail": "some error detail"},
        ])
        section = vr.to_prompt_section()
        assert "真实验证结果" in section
        assert "pytest tests/" in section
        assert "ruff check" in section
        assert "some error detail" in section


class TestExecutorVerifierInit:
    def test_defaults(self):
        v = ExecutorVerifier()
        assert v._timeout == 120
        assert v._sandbox is None
        assert v._working_dir == "."

    def test_custom_values(self):
        v = ExecutorVerifier(timeout_per_command=60, working_dir="/tmp")
        assert v._timeout == 60
        assert v._working_dir == "/tmp"


class TestValidateCommands:
    """_validate_commands——纯逻辑，无 I/O"""

    def test_allowed_command_passes(self):
        v = ExecutorVerifier()
        v._validate_commands(["pytest tests/ -q"])  # 不抛异常

    def test_disallowed_command_raises(self):
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="不在白名单"):
            v._validate_commands(["rm -rf /"])

    def test_shell_metachar_semicolon_raises(self):
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="禁止的 shell 元字符"):
            v._validate_commands(["pytest tests/; rm -rf /"])

    def test_shell_metachar_pipe_raises(self):
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["pytest | sort"])

    def test_shell_metachar_backtick_raises(self):
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["pytest `whoami`"])

    def test_python_c_disabled(self):
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="python -c 已禁用"):
            v._validate_commands(["python -c 'print(1)'"])

    def test_python_c_no_space_also_disabled(self):
        """python -c\"...\"（无空格）也被拦截."""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["python -c\"print(1)\""])

    def test_empty_command_skipped(self):
        v = ExecutorVerifier()
        v._validate_commands(["  ", "pytest"])  # 不抛异常

    def test_path_prefixed_command(self):
        """/usr/bin/pytest → 提取 pytest 再检查白名单."""
        v = ExecutorVerifier()
        v._validate_commands(["/usr/bin/pytest tests/"])  # 不抛异常

    def test_malformed_command_raises(self):
        """shlex.split 失败 → 禁止."""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="命令解析失败"):
            v._validate_commands(["'unclosed quote"])


@pytest.mark.asyncio
async def test_execute_empty_commands():
    """execute([]) → 默认 VerificationResult 无验证命令."""
    v = ExecutorVerifier()
    result = await v.execute([])
    assert result.all_passed is True
    assert result.total_count == 0


@pytest.mark.asyncio
async def test_execute_raises_on_disallowed_command():
    """execute(['rm -rf /']) → CommandNotAllowedError."""
    v = ExecutorVerifier()
    with pytest.raises(CommandNotAllowedError):
        await v.execute(["rm -rf /"])


@pytest.mark.asyncio
async def test_execute_raises_on_shell_metachar():
    """execute 检测到 shell 元字符时抛出 CommandNotAllowedError."""
    v = ExecutorVerifier()
    with pytest.raises(CommandNotAllowedError, match="禁止的 shell 元字符"):
        await v.execute(["pytest tests/; echo hack"])


class TestVerificationResultEdgeCases:
    """VerificationResult 属性/方法边缘情况。"""

    def test_failed_commands_all_failed(self):
        vr = VerificationResult(all_passed=False, results=[
            {"command": "pytest", "passed": False, "exit_code": 1},
            {"command": "ruff", "passed": False, "exit_code": 1},
        ])
        assert vr.all_passed is False
        assert vr.passed_count == 0
        assert vr.total_count == 2
        assert len(vr.failed_commands) == 2

    def test_all_passed_true(self):
        vr = VerificationResult(results=[
            {"command": "pytest", "passed": True, "exit_code": 0},
            {"command": "ruff", "passed": True, "exit_code": 0},
        ])
        assert vr.all_passed is True
        assert vr.failed_commands == []
        assert vr.passed_count == 2

    def test_to_prompt_section_failed_shows_stderr(self):
        vr = VerificationResult(all_passed=False, results=[
            {"command": "pytest", "passed": False, "exit_code": 1,
             "stderr_tail": "AssertionError: assert 0"},
        ])
        section = vr.to_prompt_section()
        assert "AssertionError" in section
        assert "❌" in section
        assert "pytest" in section

    def test_to_prompt_section_no_stderr_on_passed(self):
        vr = VerificationResult(results=[
            {"command": "pytest", "passed": True, "exit_code": 0},
        ])
        section = vr.to_prompt_section()
        assert "✅" in section
        assert "AssertionError" not in section

    def test_failed_commands_empty_when_all_passed(self):
        """全部 passed 时 failed_commands 为空列表。"""
        vr = VerificationResult(results=[{"passed": True}, {"passed": True}])
        assert vr.failed_commands == []

    def test_total_count_zero_on_empty_results(self):
        """空 results 时 total_count == 0。"""
        vr = VerificationResult(results=[])
        assert vr.total_count == 0

    def test_failed_commands_property(self):
        """failed_commands 仅返回 passed=False 的项。"""
        vr = VerificationResult(results=[
            {"command": "a", "passed": True},
            {"command": "b", "passed": False, "exit_code": 1},
            {"command": "c", "passed": False, "exit_code": 2},
            {"command": "d", "passed": True},
        ])
        assert len(vr.failed_commands) == 2
        assert vr.failed_commands[0]["command"] == "b"
        assert vr.failed_commands[1]["command"] == "c"


class TestValidateCommandsEdgeCases:
    """补充 _validate_commands 边缘用例。"""

    def test_shell_metachar_dollar_paren_raises(self):
        """$() 元字符检测。"""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="禁止的 shell 元字符"):
            v._validate_commands(["pytest $(id)"])

    def test_shell_metachar_double_ampersand_raises(self):
        """&& 元字符检测。"""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["pytest && echo hack"])

    def test_shell_metachar_double_pipe_raises(self):
        """|| 元字符检测。"""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["pytest || echo hack"])

    def test_shell_metachar_greater_raises(self):
        """> 元字符检测。"""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError):
            v._validate_commands(["pytest > /dev/null"])

    def test_validate_non_string_command_handled(self):
        """shlex.split 失败的畸形命令。"""
        v = ExecutorVerifier()
        with pytest.raises(CommandNotAllowedError, match="命令解析失败"):
            v._validate_commands(["'unclosed"])


class TestExecuteMockedRunCommand:
    """execute() 内部循环——mock _run_command 避免子进程。"""

    @pytest.mark.asyncio
    async def test_all_commands_pass(self):
        v = ExecutorVerifier()
        with patch.object(v, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                {"command": "pytest", "exit_code": 0, "passed": True,
                 "stdout_tail": "", "stderr_tail": ""},
                {"command": "ruff", "exit_code": 0, "passed": True,
                 "stdout_tail": "", "stderr_tail": ""},
            ]
            result = await v.execute(["pytest", "ruff"])
        assert result.all_passed is True
        assert result.passed_count == 2
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_one_command_fails(self):
        v = ExecutorVerifier()
        with patch.object(v, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                {"command": "pytest", "exit_code": 1, "passed": False,
                 "stdout_tail": "", "stderr_tail": "FAILED"},
                {"command": "ruff", "exit_code": 0, "passed": True,
                 "stdout_tail": "", "stderr_tail": ""},
            ]
            result = await v.execute(["pytest", "ruff"])
        assert result.all_passed is False
        assert result.passed_count == 1
        assert len(result.failed_commands) == 1

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        v = ExecutorVerifier()
        with patch.object(v, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = TimeoutError("timed out")
            result = await v.execute(["pytest"])
        assert result.all_passed is False
        assert "超时" in result.results[0]["stderr_tail"]

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self):
        v = ExecutorVerifier()
        with patch.object(v, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("unexpected error")
            result = await v.execute(["pytest"])
        assert result.all_passed is False
        assert "unexpected error" in result.results[0]["stderr_tail"]


@pytest.mark.asyncio
class TestRunCommand:
    """_run_command——mock subprocess 避免 I/O。"""

    async def test_basic_execution(self):
        """正向：命令成功 → 返回正确 dict。"""
        v = ExecutorVerifier()
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"stdout output", b""))
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            result = await v._run_command("pytest tests/")
        assert result["command"] == "pytest tests/"
        assert result["exit_code"] == 0
        assert result["passed"] is True
        assert result["stdout_tail"] == "stdout output"

    async def test_failure_exit_code(self):
        """命令失败 → exit_code != 0, passed=False。"""
        v = ExecutorVerifier()
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"FAIL: test failed"))
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await v._run_command("pytest tests/")
        assert result["exit_code"] == 1
        assert result["passed"] is False
        assert result["stderr_tail"] == "FAIL: test failed"

    async def test_timeout_during_execution(self):
        """超时 → proc.kill() + 抛出 TimeoutError。"""
        v = ExecutorVerifier()
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError())
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=None)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(TimeoutError):
                await v._run_command("pytest tests/")
        proc.kill.assert_called_once()

    async def test_returncode_none_handling(self):
        """P2-4: returncode=None → 转为 -1。"""
        v = ExecutorVerifier()
        proc = MagicMock()
        proc.returncode = None
        proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await v._run_command("pytest")
        assert result["exit_code"] == -1
        assert result["passed"] is False

    async def test_stdout_truncation(self):
        """长输出 → 截断至尾部 500 字符。"""
        v = ExecutorVerifier()
        proc = MagicMock()
        proc.returncode = 0
        long_out = b"x" * 1000
        proc.communicate = AsyncMock(return_value=(long_out, b""))
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await v._run_command("pytest")
        assert len(result["stdout_tail"]) == 500

    async def test_sandbox_execution(self):
        """Docker 沙箱执行路径。"""
        sandbox = AsyncMock()
        sandbox.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="ok", stderr=""))
        v = ExecutorVerifier(sandbox=sandbox)
        result = await v._run_command("pytest")
        assert result["passed"] is True
        assert result["exit_code"] == 0
        sandbox.run.assert_called_once()

    async def test_malformed_shlex(self):
        """shlex.split 失败 → 返回错误 dict。"""
        v = ExecutorVerifier()
        result = await v._run_command("'unclosed quote")
        assert result["exit_code"] == -1
        assert result["passed"] is False
        assert "命令解析失败" in result["stderr_tail"]
