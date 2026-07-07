"""Session API 路由.

端点:
  POST   /api/v1/sessions                 创建会话
  GET    /api/v1/sessions                 列出所有会话
  GET    /api/v1/sessions/{id}            会话详情（含聊天记录）
  PATCH  /api/v1/sessions/{id}            更新会话
  POST   /api/v1/sessions/{id}/fork       分叉会话（对话分支）
  GET    /api/v1/sessions/{id}/forks      列出子分支
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from orbit.projects.registry import ProjectRegistry
from orbit.sessions.registry import SessionRegistry

router = APIRouter(prefix="/sessions", tags=["sessions"])

_registry = SessionRegistry()
_projects = ProjectRegistry()


# ── Pydantic schemas（API 契约层，不放入 sessions/models.py）──


class SessionCreateRequest(BaseModel):
    """创建会话请求。"""

    project_name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    title: str = Field("", max_length=100, description="会话标题，可选")
    local_path: str = Field("", max_length=1000, description="项目本地路径，可选——空时从 ProjectRegistry 补")


class SessionUpdateRequest(BaseModel):
    """更新会话请求。"""

    title: str | None = Field(None, max_length=100)
    status: str | None = Field(None, pattern=r"^(active|archived)$")


class SessionForkRequest(BaseModel):
    """分叉会话请求——UX 长期 #13 对话分支。"""

    fork_at_message_index: int | None = Field(
        None, ge=0, description="从第几条消息处分叉（0-based）。None=从最新消息处分叉"
    )
    title: str = Field("", max_length=100, description="子会话标题，空时自动生成")


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
    # WHY 从 ProjectRegistry 补 local_path: 前端只传 project_name，路径需从项目注册表查
    local_path = req.local_path
    if not local_path:
        proj = _projects.get(req.project_name)
        if proj:
            local_path = proj.local_path
    rec = _registry.create(req.project_name, req.title, local_path)
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


# ── UX 长期 #13：对话分支 ─────────────────────────────


@router.post(
    "/{session_id}/fork",
    response_model=dict,
    summary="分叉会话（对话分支）",
    description="从指定消息位置分叉，创建子会话。fork_at_message_index 为 None 时从最新消息处分叉。",
    responses={404: {"description": "父会话不存在"}},
)
async def fork_session(session_id: str, req: SessionForkRequest = SessionForkRequest()) -> dict:
    """创建会话分支——UX 长期 #13。

    1. 验证父会话存在
    2. 调用 SessionRegistry.create_fork() 创建子会话
    3. 复制父会话消息到分叉点
    4. 返回子会话信息
    """
    parent = _registry.get(session_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"父会话 {session_id} 不存在",
                "error_code": "SESSION_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    # 创建子会话（DB lineage 已由 registry.create_fork 记录）
    title = req.title or f"分支: {parent.title or session_id[:8]}"
    child_id = _registry.create_fork(session_id, reason=f"forked at message #{req.fork_at_message_index}" if req.fork_at_message_index is not None else "forked at latest")

    # 更新子会话标题
    _registry.update(child_id, title=title)

    # 复制消息到分叉点
    all_messages = _registry.get_messages(session_id, limit=1000)
    fork_index = req.fork_at_message_index if req.fork_at_message_index is not None else len(all_messages) - 1
    messages_to_copy = all_messages[: fork_index + 1] if fork_index >= 0 else []

    for msg in messages_to_copy:
        _registry.add_message(
            child_id,
            role=msg.role,
            content=msg.content,
            candidates=msg.candidates,
            cross_project_warning=msg.cross_project_warning,
        )

    child = _registry.get(child_id)
    if child is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": "分叉创建失败", "error_code": "FORK_FAILED"},
        )

    return {
        "code": 0,
        "data": child.to_dict(),
        "message": "ok",
    }


@router.get(
    "/{session_id}/forks",
    response_model=dict,
    summary="列出子分支",
    description="获取指定会话的所有子分支（fork 产生的子会话）。",
)
async def list_forks(session_id: str) -> dict:
    """列出会话的所有子分支。"""
    children = _registry.get_child_sessions(session_id)
    return {
        "code": 0,
        "data": [c.to_dict() for c in children],
        "message": "ok",
    }
