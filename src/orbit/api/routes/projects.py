"""Project API 路由 (Session PR #1).

端点:
  POST   /api/v1/projects             注册或更新项目
  GET    /api/v1/projects             列出所有项目
  GET    /api/v1/projects/{name}      查询单个项目
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from orbit.projects.registry import ProjectRegistry

router = APIRouter(prefix="/projects", tags=["projects"])

_registry = ProjectRegistry()


# ── Pydantic schemas ─────────────────────────────────

class ProjectCreateRequest(BaseModel):
    """注册或更新项目请求。"""
    name: str = Field(..., min_length=1, max_length=200, description="项目名称（文件夹名）")
    local_path: str = Field(..., min_length=1, max_length=1000, description="项目文件夹绝对路径")
    repo_url: str = Field("", max_length=500)
    description: str = Field("", max_length=1000)
    tags: list[str] = Field(default_factory=list)


# ── 路由 ─────────────────────────────────────────────

@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="注册或更新项目",
    description="注册新项目或更新已有项目。local_path 必须存在且可读。",
    responses={
        400: {"description": "路径不存在"},
        403: {"description": "路径无读取权限"},
    },
)
async def register_project(req: ProjectCreateRequest) -> dict:
    # WHY 服务端验证路径：前端可能绕过或传错误路径，后端必须独立校验
    path = req.local_path
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": f"路径 {path} 不存在，请检查后重试",
                "error_code": "PATH_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    if not os.access(path, os.R_OK):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": f"路径 {path} 无读取权限",
                "error_code": "PATH_PERMISSION_DENIED",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    rec = _registry.register(
        name=req.name,
        local_path=path,
        repo_url=req.repo_url,
        description=req.description,
        tags=req.tags,
    )
    return {
        "code": 0,
        "data": rec.to_dict(),
        "message": "ok",
    }


@router.get(
    "",
    response_model=dict,
    summary="列出所有项目",
)
async def list_projects() -> dict:
    projects = _registry.list_all()
    return {
        "code": 0,
        "data": [p.to_dict() for p in projects],
        "message": "ok",
    }


@router.get(
    "/{name}",
    response_model=dict,
    summary="查询单个项目",
    responses={404: {"description": "项目不存在"}},
)
async def get_project(name: str) -> dict:
    project = _registry.get(name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"项目 {name} 不存在",
                "error_code": "PROJECT_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    return {
        "code": 0,
        "data": project.to_dict(),
        "message": "ok",
    }
