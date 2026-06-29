"""全局搜索 API (Step 9 Phase 1.3)——文件名搜索+内容搜索（ripgrep）."""
from __future__ import annotations
import asyncio, os, fnmatch
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/search", tags=["search"])

_workspace_dir: str | None = None

def set_workspace(d: str) -> None:
    global _workspace_dir; _workspace_dir = d

def _ws() -> str:
    if _workspace_dir is None: raise RuntimeError("workspace not set")
    return _workspace_dir

class SearchResult(BaseModel):
    file: str; line: int | None; context: str | None


@router.get("", response_model=list[SearchResult])
async def search(q: str = Query(..., min_length=2), type: str = Query("content"), max: int = Query(50)):
    """全局搜索。type=file 按文件名搜索，type=content 按内容搜索（使用 ripgrep）。"""
    ws = Path(_ws())
    if not ws.exists():
        raise HTTPException(status_code=500, detail="Workspace not found")
    try:
        if type == "file":
            return _search_filenames(ws, q, max)
        else:
            return await _search_content(ws, q, max)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _search_filenames(ws: Path, q: str, max_results: int) -> list[SearchResult]:
    """文件名模糊匹配——遍历项目目录。"""
    results = []
    EXCLUDE = {"__pycache__","node_modules",".git",".venv","venv","data",".orbit","dist","build","__pycache__"}
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
        proc = await asyncio.create_subprocess_exec(
            "rg", "--line-number", "--max-count=1", "--no-heading",
            "--max-count=" + str(max_results),
            q, str(ws),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        lines = stdout.decode("utf-8", errors="replace").strip().split("\n")
        results = []
        for line in lines[:max_results]:
            if not line: continue
            # rg format: file:lineno:content
            parts = line.split(":", 2)
            if len(parts) >= 2:
                f = os.path.relpath(parts[0], ws).replace("\\", "/")
                results.append(SearchResult(
                    file=f, line=int(parts[1]) if len(parts) > 1 else None,
                    context=parts[2][:200] if len(parts) > 2 else None,
                ))
        return results
    except (FileNotFoundError, asyncio.TimeoutError):
        return []  # rg 未安装或超时，返回空
