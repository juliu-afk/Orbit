"""Git 操作 API 路由 (Step 9 Phase 1)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/git", tags=["git"])
_workspace_dir: str | None = None


def set_workspace_dir(d: str) -> None:
    global _workspace_dir
    _workspace_dir = d


def _ws() -> str:
    if _workspace_dir is None:
        raise RuntimeError("workspace not set")
    return _workspace_dir


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


@router.get("/gpg-keys", response_model=list[GpgKey])
async def list_gpg_keys():
    try:
        proc = await asyncio.create_subprocess_exec(
            "gpg",
            "--list-secret-keys",
            "--keyid-format",
            "LONG",
            "--with-colons",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
    except FileNotFoundError:
        return []
    keys = []
    current = {}
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if line.startswith("sec:"):
            current = {}
            parts = line.split(":")
            if len(parts) > 4:
                current["id"] = parts[4]  # P0-3: key id from sec line
        elif line.startswith("uid:"):
            parts = line.split(":")
            ne = parts[9] if len(parts) > 9 else ""
            m = re.match(r"(.+?)\s*<(.+?)>", ne)
            if m:
                current["name"] = m.group(1).strip()
                current["email"] = m.group(2).strip()
                if "id" in current:
                    keys.append(
                        GpgKey(
                            id=current["id"],
                            name=current.get("name", ""),
                            email=current.get("email", ""),
                            fingerprint=current.get("fingerprint", ""),
                        )
                    )
        elif line.startswith("fpr:"):
            parts = line.split(":")
            current["fingerprint"] = parts[9] if len(parts) > 9 else ""
    return keys


@router.post("/commit")
async def commit(req: CommitRequest):
    ws = Path(_ws())
    if not (ws / ".git").exists():
        raise HTTPException(status_code=400, detail="Not a git repo")
    # P2-6: validate file paths
    for f in req.files:
        if ".." in f:
            raise HTTPException(status_code=400, detail=f"Invalid path: {f}")
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(ws),
        "status",
        "--porcelain",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if not stdout.strip():
        raise HTTPException(status_code=400, detail="No changes to commit")
    # P0-2: git add before commit
    add_cmd = ["git", "-C", str(ws), "add"] + (req.files if req.files else ["-A"])
    add_proc = await asyncio.create_subprocess_exec(
        *add_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, add_err = await add_proc.communicate()
    if add_proc.returncode != 0:
        raise HTTPException(
            status_code=400, detail=f"git add failed: {add_err.decode('utf-8', errors='replace')}"
        )
    cmd = ["git", "-C", str(ws), "commit"]
    if req.sign and req.gpg_key_id:
        cmd.append(f"-S{req.gpg_key_id}")
    elif req.sign:
        cmd.append("-S")
    cmd.extend(["-m", req.message])
    if req.files:
        cmd.extend(req.files)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out, err = stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise HTTPException(status_code=400, detail=f"Commit failed: {err}")
    m = re.search(r"\[[\w\-]+ ([a-f0-9]+)\]", out)
    commit_hash = m.group(1) if m else ""
    verified = False
    if req.sign:
        sp = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(ws),
            "log",
            "-1",
            "--show-signature",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        so, _ = await sp.communicate()
        verified = "Good signature" in so.decode("utf-8", errors="replace")
    return {"commit_hash": commit_hash, "verified": verified}


@router.get("/merge-conflicts")
async def get_merge_conflicts():
    ws = Path(_ws())
    if not (ws / ".git").exists():
        raise HTTPException(status_code=400, detail="Not a git repo")
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(ws),
        "diff",
        "--name-only",
        "--diff-filter=U",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    # P1-3: errors="replace" 避免非 UTF-8 路径崩
    files = stdout.decode("utf-8", errors="replace").strip().splitlines() if stdout.strip() else []
    return {"conflicts": files}
