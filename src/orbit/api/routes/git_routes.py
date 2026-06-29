"""Git 操作 API 路由 (Step 9 Phase 1).

端点:
  GET    /api/v1/git/diff              获取 Git diff (vs HEAD)
  GET    /api/v1/git/gpg-keys          列出系统 GPG 密钥
  POST   /api/v1/git/commit            Git 提交（支持 GPG 签名）
  GET    /api/v1/git/merge-conflicts   获取合并冲突
  POST   /api/v1/git/resolve-conflict  解决合并冲突
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/git", tags=["git"])

_workspace_dir: str | None = None


def set_workspace_dir(d: str) -> None:
    global _workspace_dir
    _workspace_dir = d


def _ws() -> str:
    if _workspace_dir is None:
        raise RuntimeError("workspace 未设置")
    return _workspace_dir


# ── Pydantic schemas ──


class GpgKey(BaseModel):
    id: str
    name: str
    email: str
    fingerprint: str


class CommitRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    files: list[str] = Field(default_factory=list)
    sign: bool = False
    gpg_key_id: str | None = None


class ConflictResolution(BaseModel):
    file: str = Field(..., min_length=1)
    resolution: str = Field(..., pattern=r"^(ours|theirs|custom)$")
    custom_content: str | None = None


# ── 路由 ──


@router.get("/gpg-keys", response_model=list[GpgKey])
async def list_gpg_keys():
    """列出系统 GPG 密钥（用于签名提交）。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gpg", "--list-secret-keys", "--keyid-format", "LONG",
            "--with-colons",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []  # GPG 不可用，返回空列表
    except FileNotFoundError:
        return []  # GPG 未安装

    keys: list[GpgKey] = []
    current: dict = {}
    for line in stdout.decode("utf-8", errors="replace").split("\n"):
        if line.startswith("sec:"):
            current = {}
        elif line.startswith("uid:"):
            parts = line.split(":")
            name_email = parts[9] if len(parts) > 9 else ""
            m = re.match(r"(.+?)\s*<(.+?)>", name_email)
            if m:
                current["name"] = m.group(1).strip()
                current["email"] = m.group(2).strip()
                if "id" in current:
                    keys.append(GpgKey(
                        id=current.get("id", ""),
                        name=current.get("name", ""),
                        email=current.get("email", ""),
                        fingerprint=current.get("fingerprint", ""),
                    ))
        elif line.startswith("fpr:"):
            parts = line.split(":")
            current["fingerprint"] = parts[9] if len(parts) > 9 else ""
    return keys


@router.post("/commit")
async def commit(req: CommitRequest):
    """Git 提交——可选 GPG 签名。

    WHY subprocess git commit 而非 GitPython：
    GPG 签名通过 git commit -S<keyid> 原生支持，GitPython 的签名配置复杂。
    """
    ws = Path(_ws())
    if not (ws / ".git").exists():
        raise HTTPException(status_code=400, detail="workspace 不是 git 仓库")

    # 检查工作区状态
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(ws), "status", "--porcelain",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if not stdout.strip():
        raise HTTPException(status_code=400, detail="无变更可提交")

    # 构建 commit 命令
    cmd = ["git", "-C", str(ws), "commit"]
    if req.sign and req.gpg_key_id:
        cmd.append(f"-S{req.gpg_key_id}")
    elif req.sign:
        cmd.append("-S")  # 使用默认 GPG key
    cmd.extend(["-m", req.message])
    if req.files:
        cmd.extend(req.files)

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise HTTPException(status_code=400, detail=f"提交失败: {err}")

    # 提取 commit hash
    m = re.search(r"\[[\w\-]+ ([a-f0-9]+)\]", out)
    commit_hash = m.group(1) if m else ""

    # 验证 GPG 签名
    verified = False
    if req.sign:
        sign_proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(ws), "log", "-1", "--show-signature",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        sign_out, _ = await sign_proc.communicate()
        verified = "Good signature" in sign_out.decode("utf-8", errors="replace")

    return {"commit_hash": commit_hash, "verified": verified}


@router.get("/merge-conflicts")
async def get_merge_conflicts():
    """获取当前合并冲突文件列表。"""
    ws = Path(_ws())
    if not (ws / ".git").exists():
        raise HTTPException(status_code=400, detail="workspace 不是 git 仓库")

    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(ws), "diff", "--name-only", "--diff-filter=U",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    files = stdout.decode("utf-8").strip().split("\n") if stdout.strip() else []
    return {"conflicts": files}
