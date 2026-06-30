"""文件服务 API 路由 (Step 9 Phase 1)."""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from orbit.files.service import FileService

router = APIRouter(prefix="/files", tags=["files"])
_file_service: FileService | None = None


def set_file_service(svc: FileService) -> None:
    global _file_service
    _file_service = svc


def _svc() -> FileService:
    if _file_service is None:
        raise RuntimeError("FileService not initialized")
    return _file_service


@router.get("/tree")
async def list_files():
    try:
        files = await _svc().list_files()
    except (OSError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"files": [f.model_dump() for f in files]}


@router.get("/read")
async def read_file(path: str = Query(..., min_length=1)):
    try:
        content = await _svc().read_file(path)
        language = _svc().detect_language(path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": content, "language": language}


@router.get("/diff")
async def diff_file(
    path: str = Query(..., min_length=1),
    rev_a: str = Query("HEAD"),
    rev_b: str | None = Query(None),
):
    try:
        result = await _svc().diff(path, rev_a, rev_b)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return result
