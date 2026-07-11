"""文件服务 API 路由 (Step 9 Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from orbit.files.service import FileService

router = APIRouter(prefix="/files", tags=["files"])
_file_service: FileService | None = None


class WriteFileRequest(BaseModel):
    path: str = Field(..., min_length=1, description="工作区相对路径")
    content: str = Field(..., description="文件全文内容")


def set_file_service(svc: FileService) -> None:
    global _file_service
    _file_service = svc


def _svc() -> FileService:
    if _file_service is None:
        raise RuntimeError("FileService not initialized")
    return _file_service


@router.get("/tree")
async def list_files(dir: str | None = Query(None, description="项目目录路径，为空则使用默认工作区")):
    try:
        files = await _svc().list_files(directory=dir)
    except (OSError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"files": [f.model_dump() for f in files]}, "message": "ok"}


@router.get("/read")
async def read_file(
    path: str = Query(..., min_length=1),
    dir: str | None = Query(None, description="项目目录路径，为空则使用默认工作区"),
):
    try:
        content = await _svc().read_file(path, directory=dir)
        language = _svc().detect_language(path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {"code": 0, "data": {"content": content, "language": language}, "message": "ok"}


@router.get("/diff")
async def diff_file(
    path: str = Query(..., min_length=1),
    rev_a: str = Query("HEAD"),
    rev_b: str | None = Query(None),
    dir: str | None = Query(None, description="项目目录路径，为空则使用默认工作区"),
):
    try:
        result = await _svc().diff(path, rev_a, rev_b, directory=dir)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"code": 0, "data": result, "message": "ok"}


@router.post("/write")
async def write_file(body: WriteFileRequest):
    """写文件到工作区（编辑器存盘）。

    WHY: 前端 LightEditor/RulesPanel 存盘依赖此端点。write_file 内部经 _safe_path
    做路径穿越防护（越界抛 ValueError→403），杜绝写到工作区外。
    """
    try:
        await _svc().write_file(body.path, body.content)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"code": 0, "data": {"path": body.path, "written": True}, "message": "ok"}
