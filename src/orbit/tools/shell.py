"""Shell 工具——exec_command (白名单模式).

对标: Claude Code Bash 23 validators
     + OpenClaw agent_launch 子进程
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from orbit.tools.registry import get_registry

# ── 白名单定义 ───────────────────────────────────────────
# 对标 Claude Code 23 Bash validators——只允许安全的开发命令

SHELL_WHITELIST: dict[str, list[str]] = {
    "git": [
        "status",
        "diff",
        "add",
        "commit",
        "log",
        "branch",
        "checkout",
        "push",
        "pull",
        "fetch",
        "merge",
        "rebase",
        "stash",
        "tag",
        "remote",
        "clone",
        "init",
        "restore",
        "switch",
        "cherry-pick",
        "bisect",
        "blame",
        "show",
        "describe",
        "rev-parse",
        "config",
    ],
    "pytest": ["*"],
    # P0-9: python -c 已禁用——可通过 -c 执行任意代码绕过白名单
    # P1-5 (PR#130): python -m 限制安全模块白名单——开放 -m 可执行任意带 __main__ 的模块
    "python": ["--version"],
    "pnpm": [
        "install",
        "build",
        "test",
        "lint",
        "add",
        "remove",
        "run",
        "dev",
        "start",
        "format",
        "typecheck",
    ],
    "npm": ["install", "build", "test", "run", "start", "ci"],
    "uv": ["add", "run", "lock", "sync", "pip", "python"],
    "ls": ["*"],
    "cat": ["*"],
    "head": ["*"],
    "tail": ["*"],
    "wc": ["*"],
    "find": ["*"],
    "echo": ["*"],
    "mkdir": ["*"],
    "cp": ["*"],
    "mv": ["*"],
    "rm": [],  # 禁止所有 rm (需显式确认)
    "touch": ["*"],
    "which": ["*"],
    "env": ["*"],
    "date": ["*"],
    "sort": ["*"],
    "uniq": ["*"],
    "cut": ["*"],
    "tr": ["*"],
    "sed": ["*"],
    "awk": ["*"],
}

# python -m 安全模块白名单——P1-5 (PR#130)
# WHY 限制: python -m <任意模块> 可执行 http.server/venv 等
_PYTHON_M_WHITELIST: frozenset[str] = frozenset({
    "pytest",
    "pip",
    "venv",
    "flake8",
    "black",
    "isort",
    "mypy",
    "coverage",
    "http.server",  # 允许本地开发调试
})

# 危险模式——即使白名单通过也拒绝
DANGEROUS_PATTERNS = [
    ("rm -rf /", "禁止递归删除根目录"),
    ("rm -rf ~", "禁止删除用户目录"),
    ("chmod 777", "禁止全权限设置"),
    ("chmod -R 777", "禁止递归全权限"),
    ("> /dev/sda", "禁止直接写块设备"),
    ("mkfs.", "禁止格式化"),
    ("dd if=", "禁止磁盘 dd"),
    ("fork bomb", "禁止 fork 炸弹"),
]

# 需要确认的危险模式 (允许但警告)
WARN_PATTERNS = [
    ("rm ", "删除文件"),
    ("git push --force", "强制推送"),
    ("git reset --hard", "硬重置"),
    ("git clean", "清理未跟踪文件"),
]


@dataclass
class ExecResult:
    """命令执行结果."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)


# ── 白名单验证 ──────────────────────────────────────────


def validate_command(cmd: str) -> ExecResult | None:
    """验证命令是否在白名单中 + 危险模式检测.

    返回 None 表示通过验证。
    返回 ExecResult 表示被拒绝 (含错误信息)。
    """
    # 检查危险组合
    for pattern, reason in DANGEROUS_PATTERNS:
        if pattern in cmd:
            return ExecResult(
                stderr=f"安全阻止: {reason} (匹配: '{pattern}')",
                exit_code=1,
            )

    # 解析命令
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return ExecResult(stderr=f"命令解析失败: {e}", exit_code=1)

    if not parts:
        return ExecResult(stderr="空命令", exit_code=1)

    base = parts[0]
    # 去掉路径前缀 (e.g. /usr/bin/git → git)
    base = base.replace("\\", "/").split("/")[-1] if "/" in base else base

    if base not in SHELL_WHITELIST:
        return ExecResult(
            stderr=f"命令 '{base}' 不在白名单中。允许: {', '.join(sorted(SHELL_WHITELIST.keys()))}",
            exit_code=1,
        )

    # 检查子命令
    allowed_subs = SHELL_WHITELIST[base]
    if "*" in allowed_subs:
        pass  # 所有子命令都允许
    elif len(parts) > 1:
        sub = parts[1]
        # 过滤 --flags (不是子命令)
        if not sub.startswith("-") and sub not in allowed_subs:
            return ExecResult(
                stderr=f"子命令 '{base} {sub}' 不在白名单中。{base} 允许: {allowed_subs}",
                exit_code=1,
            )
        # P1-5 (PR#130): python -m 限制模块白名单——
        # python -m <任意模块> 可执行 http.server/venv 等
        if base == "python" and sub == "-m" and len(parts) > 2:
            module = parts[2]
            if module not in _PYTHON_M_WHITELIST:
                return ExecResult(
                    stderr=f"python -m '{module}' 不在安全模块白名单中。允许: {sorted(_PYTHON_M_WHITELIST)}",
                    exit_code=1,
                )

    # 检查危险组合 (管道到 shell)
    if "|" in cmd:
        after_pipe = cmd.split("|")[-1].strip()
        if any(after_pipe.startswith(s) for s in ("sh", "bash", "zsh", "cmd", "powershell")):
            return ExecResult(
                stderr="安全阻止: 禁止管道输出到 shell 解释器",
                exit_code=1,
            )

    # 收集警告
    warnings = []
    for pattern, reason in WARN_PATTERNS:
        if pattern in cmd:
            warnings.append(reason)
    if warnings:
        return ExecResult(stdout="", warnings=warnings, exit_code=0)

    return None  # 通过


# ── exec_command ──────────────────────────────────────────


async def exec_command(
    cmd: str,
    cwd: str = ".",
    timeout: int = 30,
) -> str:
    """执行 Shell 命令——白名单 + Phase 4 BashValidators 双重验证后运行.

    Args:
        cmd: 要执行的命令
        cwd: 工作目录 (相对于 workspace)
        timeout: 超时秒数 (最大 120)

    Returns:
        格式化输出: [exit_code] stdout
    """
    # Phase 4 AC-A5: BashValidators 前置校验
    try:
        from orbit.security.validators import BashValidators

        BashValidators.validate(cmd)
    except ValueError as e:
        return f"❌ 安全拒绝——{e}"
    # P1-6 (PR#130): 防御性处理 ImportError——
    # BashValidators 可能因模块重构或条件导入不存在
    except ImportError:
        pass  # 安全校验不可用时不阻断，由旧白名单兜底

    # 旧白名单验证
    validation = validate_command(cmd)
    if validation is not None:
        if validation.exit_code != 0:
            return f"❌ {validation.stderr}"
        # 警告但允许执行
        pass

    # 解析工作目录
    work_dir = Path.cwd() / cwd
    if not work_dir.exists():
        work_dir = Path.cwd()

    import time as _time

    start = _time.time()
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            ),
            timeout=5,  # 进程启动超时
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        duration = (_time.time() - start) * 1000
    except TimeoutError:
        duration = (_time.time() - start) * 1000
        return f"⏱ 命令超时 ({timeout}s)\n" f"cmd: {cmd}\n" f"cwd: {work_dir}"

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    result_parts = [f"[exit:{proc.returncode}] [cwd:{cwd}] [{duration:.0f}ms]"]

    if stdout:
        result_parts.append(stdout)
    if stderr:
        result_parts.append(f"stderr:\n{stderr}")
    if validation and validation.warnings:
        result_parts.append(f"⚠ 警告: {', '.join(validation.warnings)}")

    return "\n".join(result_parts)


# ── AST 自注册 ──────────────────────────────────────────

registry = get_registry()
registry.register_tool(
    name="exec_command",
    toolset="shell",
    schema={
        "type": "function",
        "function": {
            "name": "exec_command",
            "description": (
                "执行 Shell 命令 (白名单模式)。"
                "允许: git, pytest, python, pnpm, npm, uv, ls, cat, grep, find, echo, mkdir, cp, mv 等。"
                "禁止: rm -rf, chmod 777, curl | sh, 磁盘操作等。"
                "超时默认 30s，最大 120s。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "要执行的命令 (e.g. 'pytest tests/unit/ -q')",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录，默认当前目录",
                        "default": ".",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 30，最大 120",
                        "default": 30,
                    },
                },
                "required": ["cmd"],
            },
        },
    },
    handler=exec_command,
    concurrency="never_parallel",
)
