"""文件服务 API 路由 (Step 9 Phase 1).

端点:
  GET /api/v1/files/tree   文件树（含审查状态）
  GET /api/v1/files/read   读取文件内容
  GET /api/v1/files/diff   获取文件 diff
"""

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
        raise RuntimeError("FileService 未初始化")
    return _file_service


@router.get("/tree")
async def list_files(task_id: str | None = Query(None)):
    """列出项目文件树。task_id 非空时仅列出该 task 涉及的文件。"""
    try:
        files = await _svc().list_files(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"files": [f.model_dump() for f in files]}


@router.get("/read")
async def read_file(path: str = Query(..., min_length=1)):
    """读取文件内容。"""
    try:
        content = await _svc().read_file(path)
        language = _svc().detect_language(path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"content": content, "language": language}


@router.get("/diff")
async def diff_file(
    path: str = Query(..., min_length=1),
    rev_a: str = Query("HEAD"),
    rev_b: str | None = Query(None),
):
    """获取文件 diff。"""
    try:
        result = await _svc().diff(path, rev_a, rev_b)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return result
