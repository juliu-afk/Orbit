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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orbit.sandbox.executor import Sandbox

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
            except asyncio.TimeoutError:
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
        """验证命令白名单——安全基线。"""
        for cmd in commands:
            cmd_name = cmd.strip().split()[0] if cmd.strip() else ""
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

        # 本地 subprocess 执行
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._working_dir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        return {
            "command": cmd,
            "exit_code": proc.returncode or 0,
            "passed": proc.returncode == 0,
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
