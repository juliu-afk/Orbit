"""集成终端 API (Step 9 Phase 2.5)——命令执行+输出流。"""
from __future__ import annotations
import asyncio, os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/terminal", tags=["terminal"])

_workspace_dir: str | None = None
ALLOWED_COMMANDS = {"pytest","ruff","mypy","git","ls","dir","cat","echo","python","poetry","pnpm","make","grep","head","tail","wc"}

def set_workspace(d: str) -> None:
    global _workspace_dir; _workspace_dir = d

def _ws() -> str:
    if _workspace_dir is None: raise RuntimeError("workspace not set")
    return _workspace_dir

class ExecRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=2000)
    cwd: str = "."
    timeout: int = Field(30, ge=1, le=300)

class ExecResult(BaseModel):
    exit_code: int; stdout: str; stderr: str; duration_ms: float


@router.post("/exec", response_model=ExecResult)
async def exec_command(req: ExecRequest):
    """执行终端命令——白名单限制+30s超时。"""
    ws = _ws()
    cmd_parts = req.command.split()
    if not cmd_parts:
        raise HTTPException(status_code=400, detail="Empty command")
    # 白名单检查
    if cmd_parts[0] not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=403, detail=f"Command not allowed: {cmd_parts[0]}")
    cwd = os.path.join(ws, req.cwd) if req.cwd != "." else ws
    if not os.path.isdir(cwd):
        raise HTTPException(status_code=400, detail=f"Directory not found: {req.cwd}")
    import time as _time
    start = _time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        return ExecResult(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace")[-50000:],
            stderr=stderr.decode("utf-8", errors="replace")[-10000:],
            duration_ms=(_time.monotonic() - start) * 1000,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail=f"Command timed out ({req.timeout}s)")
