"""全局搜索 API (Step 9 Phase 1.3)——文件名搜索+内容搜索（ripgrep）."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/search", tags=["search"])

_workspace_dir: str | None = None
MAX_RESULTS = 200  # P2: 搜索结果上限


def set_workspace(d: str) -> None:
    global _workspace_dir
    _workspace_dir = d


def _ws() -> str:
    if _workspace_dir is None:
        raise RuntimeError("workspace not set")
    return _workspace_dir


class SearchResult(BaseModel):
    file: str
    line: int | None
    context: str | None


@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=2),
    search_type: str = Query("content"),
    max_results: int = Query(50, ge=1, le=MAX_RESULTS),
):
    """全局搜索。search_type=file 按文件名，search_type=content 按内容（ripgrep）。"""
    ws = Path(_ws())
    if not ws.exists():
        raise HTTPException(status_code=500, detail="Workspace not found")
    try:
        if search_type == "file":
            return await asyncio.to_thread(_search_filenames, ws, q, max_results)
        else:
            return await _search_content(ws, q, max_results)
    except (OSError, RuntimeError) as e:
        # P2: 不泄露内部路径，返回通用错误
        import structlog

        structlog.get_logger().error("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Search failed")


def _search_filenames(ws: Path, q: str, max_results: int) -> list[SearchResult]:
    """文件名模糊匹配——在独立线程中运行（通过 asyncio.to_thread 调用）。"""
    results = []
    EXCLUDE = {
        "__pycache__",
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "data",
        ".orbit",
        "dist",
        "build",
        "__pycache__",
    }
    q_lower = q.lower()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in EXCLUDE and not d.startswith(".")]
        for f in files:
            if fnmatch.fnmatch(f.lower(), f"*{q_lower}*"):
                rel = os.path.relpath(os.path.join(root, f), ws).replace("\\", "/")
                results.append(SearchResult(file=rel, line=None, context=None))
                if len(results) >= max_results:
                    return results
    return results


async def _search_content(ws: Path, q: str, max_results: int) -> list[SearchResult]:
    """内容搜索——使用 rg (ripgrep) 子进程。"""
    try:
        # P2: 安全防护——禁止 rg 参数注入，q 通过位置参数传递
        proc = await asyncio.create_subprocess_exec(
            "rg",
            "--line-number",
            "--no-heading",
            "--max-count",
            str(max_results),
            "--",
            q,
            str(ws),  # -- 分隔符防止 q 被解析为 rg 参数
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
        results = []
        for line in lines[:max_results]:
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 2:
                f = os.path.relpath(parts[0], ws).replace("\\", "/")
                results.append(
                    SearchResult(
                        file=f,
                        line=int(parts[1]) if len(parts) > 1 else None,
                        context=parts[2][:200] if len(parts) > 2 else None,
                    )
                )
        return results
    except (FileNotFoundError, asyncio.TimeoutError):
        return []
