"""Session API 路由 (Session PR #1).

端点:
  POST   /api/v1/sessions             创建会话
  GET    /api/v1/sessions             列出所有会话
  GET    /api/v1/sessions/{id}        会话详情（含聊天记录）
  PATCH  /api/v1/sessions/{id}        更新会话
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from orbit.sessions.registry import SessionRegistry

router = APIRouter(prefix="/sessions", tags=["sessions"])

_registry = SessionRegistry()


# ── Pydantic schemas（API 契约层，不放入 sessions/models.py）──


class SessionCreateRequest(BaseModel):
    """创建会话请求。"""

    project_name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    title: str = Field("", max_length=100, description="会话标题，可选")


class SessionUpdateRequest(BaseModel):
    """更新会话请求。"""

    title: str | None = Field(None, max_length=100)
    status: str | None = Field(None, pattern=r"^(active|archived)$")


class SessionResponse(BaseModel):
    """会话响应。"""

    session_id: str
    project_name: str
    local_path: str = ""  # 项目路径——区分同名文件夹
    title: str
    status: str
    created_at: float
    updated_at: float


class SessionDetailResponse(BaseModel):
    """会话详情（含聊天记录）。"""

    session: SessionResponse
    messages: list[dict]


# ── 路由 ─────────────────────────────────────────────


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="创建会话",
    description="为指定项目创建新 Session。项目必须已在 ProjectRegistry 中注册。",
)
async def create_session(req: SessionCreateRequest) -> dict:
    rec = _registry.create(req.project_name, req.title)
    return {
        "code": 0,
        "data": rec.to_dict(),
        "message": "ok",
    }


@router.get(
    "",
    response_model=dict,
    summary="列出所有会话",
)
async def list_sessions(status_filter: str | None = None) -> dict:
    """列出现有会话，按更新时间降序。可选 ?status=active 或 archived。"""
    sessions = _registry.list_all(status=status_filter)
    return {
        "code": 0,
        "data": [s.to_dict() for s in sessions],
        "message": "ok",
    }


@router.get(
    "/{session_id}",
    response_model=dict,
    summary="获取会话详情",
    responses={404: {"description": "会话不存在"}},
)
async def get_session(session_id: str) -> dict:
    """返回 Session 元数据 + 最近 50 条聊天记录。"""
    rec = _registry.get(session_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"会话 {session_id} 不存在",
                "error_code": "SESSION_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    messages = _registry.get_messages(session_id, limit=50)
    return {
        "code": 0,
        "data": {
            "session": rec.to_dict(),
            "messages": [m.to_dict() for m in messages],
        },
        "message": "ok",
    }


@router.patch(
    "/{session_id}",
    response_model=dict,
    summary="更新会话",
    responses={404: {"description": "会话不存在"}},
)
async def update_session(session_id: str, req: SessionUpdateRequest) -> dict:
    """更新 Session 的 title 或 status。archived 为终态不可逆。"""
    rec = _registry.get(session_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"会话 {session_id} 不存在",
                "error_code": "SESSION_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    kwargs: dict = {}
    if req.title is not None:
        kwargs["title"] = req.title
    if req.status is not None:
        kwargs["status"] = req.status
    try:
        updated = _registry.update(session_id, **kwargs)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": str(e),
                "error_code": "SESSION_ARCHIVED_IMMUTABLE",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ) from e
    return {
        "code": 0,
        "data": updated.to_dict() if updated else None,
        "message": "ok",
    }
