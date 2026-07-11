"""记忆库浏览 API 路由——前端 RulesPanel 记忆列表。

WHY: 记忆库采用文件存储（.orbit/memory/*.md，人可读），非 SQLite。
本路由把工作区下的记忆 markdown 文件列成 [{id,type,text,time}] 供前端浏览。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/memory", tags=["memory"])
_workspace: str | None = None


def set_workspace(ws: str) -> None:
    global _workspace
    _workspace = ws


@router.get("/list")
async def list_memories():
    """列出工作区记忆库中的所有 markdown 记忆文件。

    数据源：{workspace}/.orbit/memory/*.md。目录不存在时返回空列表（新项目尚无记忆）。
    """
    ws = _workspace or os.getcwd()
    mem_dir = Path(ws) / ".orbit" / "memory"
    items: list[dict[str, str]] = []
    if mem_dir.is_dir():
        # 按修改时间倒序——最近更新的记忆排在前
        for f in sorted(mem_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            # time 用 ISO 格式的修改时间；type 用文件名（stem），前端据此分类展示
            mtime = f.stat().st_mtime
            iso = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            items.append({"id": f.stem, "type": f.stem, "text": text, "time": iso})
    return {"code": 0, "data": items, "message": "ok"}
