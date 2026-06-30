"""Git Blame API (Step 9 Phase 2.1)——每行标注作者（Agent vs Human）."""

from __future__ import annotations
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

# P1-1: Agent 邮箱后缀白名单——避免字符串包含误报
AGENT_EMAIL_SUFFIXES = ("@anthropic.com", "noreply.github.com", "copilot.github.com", "@openai.com")


def _is_agent_author(author: str) -> bool:
    """通过作者名+邮箱综合判定。author 可能是 'Name <email>' 格式。"""
    if "<" in author:
        return _is_agent_email(author.split("<")[1].rstrip(">"))
    return False


def _is_agent_email(email: str) -> bool:
    return any(email.lower().endswith(s) for s in AGENT_EMAIL_SUFFIXES)


router = APIRouter(prefix="/git", tags=["blame"])

_workspace_dir: str | None = None


def set_workspace(d: str) -> None:
    global _workspace_dir
    _workspace_dir = d


def _ws() -> str:
    if _workspace_dir is None:
        raise RuntimeError("workspace not set")
    return _workspace_dir


@router.get("/blame")
async def get_blame(file: str = Query(...)):
    """返回文件每行的 blame 信息——rev + author + time。"""
    ws = Path(_ws())
    target = (ws / file).resolve()
    # P0-1: 使用 is_relative_to 替代 startswith——防止前缀攻击
    ws_resolved = ws.resolve()
    if not target.is_relative_to(ws_resolved):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(ws),
            "blame",
            "--line-porcelain",
            str(target),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # P1-4: 30s 超时防止大文件 hang
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode != 0:
            # P1-3: 记录日志+返回 502，而非静默吞错
            import structlog

            structlog.get_logger().warning(
                "git_blame_failed",
                rc=proc.returncode,
                stderr=stderr.decode("utf-8", errors="replace")[:200],
            )
            raise HTTPException(status_code=502, detail="Git blame failed")
        lines = []
        current = {}
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if line.startswith("\t"):
                current["content"] = line[1:]
                lines.append(dict(current))
                current = {}
            elif " " in line:
                k, v = line.split(" ", 1)
                if k == "author":
                    current["author"] = v
                elif k == "author-time":
                    current["time"] = v
                elif k == "author-mail":
                    current["email"] = v
                    # R2-1: OR 逻辑——邮箱后缀匹配追加，不覆盖作者名判定
                    current["is_agent"] = current.get("is_agent", False) or _is_agent_email(v)
        return lines
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Git blame timed out (>30s)")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="git not found")
