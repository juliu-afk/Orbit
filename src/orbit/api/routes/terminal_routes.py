"""集成终端 API (Step 9 Phase 2.5)——命令执行+输出流。"""

from __future__ import annotations

import asyncio
import os
import shlex

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orbit.api.routes._workspace import _ws, set_workspace  # noqa: E402
from orbit.core.security_constants import SHELL_METACHARACTERS

router = APIRouter(prefix="/terminal", tags=["terminal"])

ALLOWED_COMMANDS = {
    "pytest",
    "ruff",
    "mypy",
    "git",
    "ls",
    "dir",
    "cat",
    "echo",
    "python",
    "poetry",
    "pnpm",
    "make",
    "grep",
    "head",
    "tail",
    "wc",
}


class ExecRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=2000)
    cwd: str = "."
    timeout: int = Field(30, ge=1, le=300)


class ExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float


@router.post("/exec", response_model=ExecResult)
async def exec_command(req: ExecRequest):
    """执行终端命令——白名单限制+30s超时。

    安全基线（Issue #126 + PR #130 review）:
    - shlex.split 防引号绕过
    - python -c 禁用
    - shell 元字符拒绝
    - cwd 路径遍历防护
    - 超时后 wait() 防僵尸进程
    """
    ws = _ws()
    # P0-1 (PR#130): shlex.split 防引号绕过——str.split 不处理 shell 引号语法
    try:
        cmd_parts = shlex.split(req.command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"命令解析失败: {e}")

    if not cmd_parts:
        raise HTTPException(status_code=400, detail="Empty command")
    # 白名单检查
    if cmd_parts[0] not in ALLOWED_COMMANDS and cmd_parts[0] not in {"./", "../"}:
        raise HTTPException(status_code=403, detail=f"Command not allowed: {cmd_parts[0]}")
    # P0-2: 阻止 python -c 绕过白名单执行任意代码
    if cmd_parts[0] == "python" and any(a == "-c" for a in cmd_parts[1:]):
        raise HTTPException(status_code=403, detail="python -c 已禁用——安全基线")
    # P0-2: 阻止 shell 元字符注入（; | && $() ``）
    for arg in cmd_parts[1:]:
        if any(m in arg for m in SHELL_METACHARACTERS):
            raise HTTPException(
                status_code=403, detail=f"Shell 元字符已禁用: {arg}"
            )
    # P1-1 (PR#130): cwd 路径遍历防护——禁止通过 ../ 逃逸 workspace
    _raw_cwd = os.path.normpath(os.path.join(ws, req.cwd)) if req.cwd != "." else ws
    if os.path.commonpath([ws, _raw_cwd]) != os.path.normpath(ws):
        raise HTTPException(status_code=403, detail="cwd 超出 workspace")
    cwd = _raw_cwd if os.path.isdir(_raw_cwd) else ws
    import time

    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace")[-50000:],
            stderr=stderr.decode("utf-8", errors="replace")[-10000:],
            duration_ms=(time.monotonic() - start) * 1000,
        )
    except TimeoutError:
        proc.kill()
        # P1-2 (PR#130): wait() 防止僵尸进程
        await proc.wait()
        raise HTTPException(status_code=504, detail=f"Command timed out ({req.timeout}s)")
