"""ExecutorVerifier——实际执行验证命令并收集结果。

对标 GoalJudge v3+ 真实验证: 不只看 transcript，实际跑 pytest/lint/tsc。

安全基线:
- 验证命令白名单——防止命令注入
- 超时控制——防止验证命令卡死
- 可选 Docker 沙箱隔离

WHY 独立类: 可 mock（测试）/ 可沙箱（Docker 隔离）/ 可超时控制。
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from orbit.core.security_constants import SHELL_METACHARACTERS

if TYPE_CHECKING:
    pass

logger = structlog.get_logger("orbit.goal")

# 验证命令白名单——安全基线
ALLOWED_VERIFICATION_COMMANDS: frozenset[str] = frozenset(
    {
        "pytest",
        "python",
        "npm",
        "pnpm",
        "tsc",
        "eslint",
        "ruff",
        "mypy",
        "cargo",
        "go",
        "make",
        "pre-commit",
    }
)


class CommandNotAllowedError(ValueError):
    """验证命令不在白名单中。"""

    pass


@dataclass
class VerificationResult:
    """验证执行结果。"""

    all_passed: bool = True
    results: list[dict] = field(default_factory=list)

    @property
    def failed_commands(self) -> list[dict]:
        return [r for r in self.results if not r.get("passed", False)]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.get("passed", False))

    @property
    def total_count(self) -> int:
        return len(self.results)

    def to_prompt_section(self) -> str:
        """生成注入 GoalJudge prompt 的验证结果段落。"""
        if not self.results:
            return "（无验证命令）"
        lines = ["## 真实验证结果"]
        for r in self.results:
            icon = "✅" if r.get("passed") else "❌"
            lines.append(
                f"- {icon} `{r.get('command', '?')}` → exit_code={r.get('exit_code', '?')}"
            )
            if not r.get("passed"):
                stderr = r.get("stderr_tail", "")
                if stderr:
                    lines.append(f"  stderr: {stderr[:200]}")
        return "\n".join(lines)


class ExecutorVerifier:
    """执行验证器——实际运行验证命令并收集结果。

    Usage:
        verifier = ExecutorVerifier(timeout_per_command=120)
        result = await verifier.execute(["pytest tests/ -q", "npm run lint"])
        if result.all_passed:
            # 验证通过
    """

    def __init__(
        self,
        timeout_per_command: int = 120,  # 秒
        sandbox: Any = None,  # Sandbox——可选 Docker 隔离
        working_dir: str = ".",
    ) -> None:
        self._timeout = timeout_per_command
        self._sandbox = sandbox
        self._working_dir = working_dir

    async def execute(self, commands: list[str]) -> VerificationResult:
        """依次执行验证命令，收集 exit_code + stdout + stderr。

        验证命令必须通过白名单校验——防止命令注入。

        Args:
            commands: 验证命令列表，如 ["pytest tests/ -q", "npm run lint"]

        Returns:
            VerificationResult: all_passed + 每命令详细结果

        Raises:
            CommandNotAllowedError: 命令不在白名单中
        """
        if not commands:
            return VerificationResult(all_passed=True)

        # 安全校验——白名单
        self._validate_commands(commands)

        results = []
        all_passed = True

        for cmd in commands:
            try:
                cmd_result = await self._run_command(cmd)
            except TimeoutError:
                logger.warning("verification_command_timeout", command=cmd)
                cmd_result = {
                    "command": cmd,
                    "exit_code": -1,
                    "passed": False,
                    "stdout_tail": "",
                    "stderr_tail": f"命令超时 ({self._timeout}s)",
                }
            except Exception as e:
                logger.error("verification_command_error", command=cmd, error=str(e))
                cmd_result = {
                    "command": cmd,
                    "exit_code": -1,
                    "passed": False,
                    "stdout_tail": "",
                    "stderr_tail": str(e)[:500],
                }

            results.append(cmd_result)
            all_passed = all_passed and cmd_result.get("passed", False)

        logger.info(
            "verification_complete",
            total=len(results),
            passed=sum(1 for r in results if r.get("passed")),
            all_passed=all_passed,
        )
        return VerificationResult(all_passed=all_passed, results=results)

    # ── 内部 ──────────────────────────────────────────

    def _validate_commands(self, commands: list[str]) -> None:
        """验证命令白名单 + shell 元字符检测——安全基线。

        WHY 双重验证: Issue #126 P0-5——仅检查命令名不足以防止注入，
        `python -c "import os; os.system('rm -rf /')"` 通过白名单但可执行任意代码。
        """
        for cmd in commands:
            cmd_stripped = cmd.strip()
            if not cmd_stripped:
                continue

            # 检测 shell 元字符（共享常量 orbit.core.security_constants）
            for meta in SHELL_METACHARACTERS:
                if meta in cmd_stripped:
                    raise CommandNotAllowedError(
                        f"验证命令包含禁止的 shell 元字符 '{meta}': {cmd_stripped[:80]}"
                    )

            # P1-3 (PR#130): 用 shlex.split 精确检测 python -c——
            # 字符串匹配 " -c " 可被 python -c"print(1)"（无空格）绕过
            try:
                parts = shlex.split(cmd_stripped)
            except ValueError as e:
                raise CommandNotAllowedError(f"命令解析失败: {e}")

            if parts and parts[0] == "python":
                if any(a == "-c" for a in parts[1:]):
                    raise CommandNotAllowedError(
                        "python -c 已禁用——安全基线，请使用 pytest/ruff/mypy 等专用工具"
                    )

            cmd_name = parts[0] if parts else ""
            # 去除路径前缀: /usr/bin/pytest → pytest
            if "/" in cmd_name:
                cmd_name = cmd_name.rsplit("/", 1)[-1]
            if cmd_name not in ALLOWED_VERIFICATION_COMMANDS:
                raise CommandNotAllowedError(
                    f"验证命令 '{cmd_name}' 不在白名单中。"
                    f"允许的命令: {sorted(ALLOWED_VERIFICATION_COMMANDS)}"
                )

    async def _run_command(self, cmd: str) -> dict:
        """执行单个命令——subprocess 或 Docker 沙箱。

        WHY 尾部截断: 完整 stdout 可能非常大（万行测试输出），
        只保留尾部 500 字符给 GoalJudge 做判定。
        """
        if self._sandbox:
            return await self._run_in_sandbox(cmd)

        # P1-4 (PR#130): create_subprocess_exec 替代 create_subprocess_shell——
        # 消除 shell 解析层，防止验证逻辑被绕过后的命令注入
        try:
            cmd_parts = shlex.split(cmd)
        except ValueError as e:
            return {
                "command": cmd,
                "exit_code": -1,
                "passed": False,
                "stdout_tail": "",
                "stderr_tail": f"命令解析失败: {e}",
            }

        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._working_dir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()  # 防僵尸进程
            raise

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        # P2-4 (PR#130): returncode 显式 None 检查——
        # `returncode or 0` 在 returncode=None 时错误返回 0(passed=True)
        _rc = proc.returncode if proc.returncode is not None else -1
        return {
            "command": cmd,
            "exit_code": _rc,
            "passed": _rc == 0,
            "stdout_tail": stdout_str[-500:] if len(stdout_str) > 500 else stdout_str,
            "stderr_tail": stderr_str[-500:] if len(stderr_str) > 500 else stderr_str,
        }

    async def _run_in_sandbox(self, cmd: str) -> dict:
        """Docker 沙箱执行——安全隔离。"""
        # 委托给 Sandbox 模块
        result = await self._sandbox.run(cmd, timeout=self._timeout)
        return {
            "command": cmd,
            "exit_code": result.exit_code,
            "passed": result.exit_code == 0,
            "stdout_tail": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
            "stderr_tail": result.stderr[-500:] if len(result.stderr) > 500 else result.stderr,
        }
