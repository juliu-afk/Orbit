"""任务路由（Step 1.1）。

MVP 阶段：仅定义路由 + 请求/响应校验，返回 mock 响应。
真实调度逻辑在 Step 5.x 接入。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from orbit.api.schemas.task import (
    HTTPExceptionDetail,
    TaskCreateRequest,
    TaskState,
    TaskStatusResponse,
)
from orbit.core.config import settings

router = APIRouter(prefix="/tasks", tags=["tasks"])

# WHY 进程内 mock 存储：MVP 阶段不依赖数据库，仅验证 API 契约。
# Step 2.2 接入检查点后替换为持久化存储。
_mock_store: dict[str, TaskStatusResponse] = {}


@router.post(
    "",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="创建任务",
    description="提交 PRD 创建任务，返回初始 IDLE 状态。prd 长度 10-5000。",
)
async def create_task(req: TaskCreateRequest) -> TaskStatusResponse:
    import uuid

    now = datetime.now(timezone.utc)
    resp = TaskStatusResponse(
        task_id=uuid.uuid4().hex,
        state=TaskState.IDLE,
        progress=0.0,
        result=None,
        created_at=now,
        updated_at=now,
    )
    _mock_store[resp.task_id] = resp
    return resp


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询任务状态",
    responses={
        404: {"model": HTTPExceptionDetail, "description": "任务不存在"},
    },
)
async def get_task(task_id: str) -> TaskStatusResponse:
    # task_id 格式由路由层校验失败时由 FastAPI 自动返回 422，
    # 这里仅处理"格式对但不存在"的 404 情况。
    task = _mock_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"任务 {task_id} 不存在",
                "error_code": "TASK_NOT_FOUND",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    return task


@router.post(
    "/{task_id}/cancel",
    response_model=TaskStatusResponse,
    summary="取消任务",
    responses={
        404: {"model": HTTPExceptionDetail, "description": "任务不存在"},
        409: {"model": HTTPExceptionDetail, "description": "任务已终态无法取消"},
    },
)
async def cancel_task(task_id: str) -> TaskStatusResponse:
    task = _mock_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"任务 {task_id} 不存在",
                "error_code": "TASK_NOT_FOUND",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    # WHY 终态不可取消：DONE/FAILED 是不可逆状态，取消已完成的任务语义错误。
    # 调度器（Step 5.x）也必须遵守此契约。
    if task.state in (TaskState.DONE, TaskState.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": f"任务 {task_id} 处于终态 {task.state.value}，无法取消",
                "error_code": "INVALID_STATE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    task.updated_at = datetime.now(timezone.utc)
    _mock_store[task_id] = task
    return task