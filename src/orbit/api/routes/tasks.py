"""任务路由（PR3：桩变真）。

从 mock 桩改为真实调度器接线：
- 状态读取走 CheckpointManager（真实任务生命周期），不再是进程内 mock dict
- 取消走 Scheduler.cancel_task（真取消运行中 asyncio 任务 + 写 CANCELLED 检查点）
- POST 创建任务并写 IDLE 检查点；POST /{id}/run 显式触发真实后台调度
- session_id/project_name/created_at 不在检查点，单独存 _task_records
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from orbit.api.schemas.task import (
    HTTPExceptionDetail,
    TaskCreateRequest,
    TaskState,
    TaskStatusResponse,
)
from orbit.checkpoint.manager import CheckpointData
from orbit.sessions.registry import SessionRegistry

router = APIRouter(prefix="/tasks", tags=["tasks"])

# 任务元数据（session_id/project_name/created_at/prd）——检查点不存这些，单独保留。
_task_records: dict[str, dict[str, object]] = {}
_MAX_TASK_RECORDS = 1000  # P2-1: 容量上限，超限淘汰最旧
_session_registry = SessionRegistry()

_TERMINAL = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}


def _scheduler(request: Request):
    # 优先 app.state；create_app() 新实例无 state 时回退到 main 模块级单例（同一个 _scheduler）
    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        from orbit.api.main import _scheduler as _module_scheduler

        sched = _module_scheduler
    if sched is None or sched.checkpoint is None:
        raise HTTPException(status_code=503, detail="Scheduler 未初始化")
    return sched


def _not_found(task_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "detail": f"任务 {task_id} 不存在",
            "error_code": "TASK_NOT_FOUND",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def _to_response(task_id: str, ckpt: CheckpointData) -> TaskStatusResponse:
    """检查点 + 元数据 → TaskStatusResponse。"""
    meta = _task_records.get(task_id, {})
    # result: 优先检查点 context 里的 CODING 产物
    artifacts = ckpt.context.get("artifacts", {}) if isinstance(ckpt.context, dict) else {}
    result = artifacts.get("CODING") if isinstance(artifacts, dict) else None
    created = meta.get("created_at")
    return TaskStatusResponse(
        task_id=task_id,
        state=TaskState(ckpt.state),
        progress=ckpt.progress,
        result=result,
        session_id=str(meta.get("session_id", "")),
        project_name=str(meta.get("project_name", "")),
        created_at=created if isinstance(created, datetime) else datetime.fromtimestamp(ckpt.updated_at, UTC),
        updated_at=datetime.fromtimestamp(ckpt.updated_at, UTC),
    )


async def create_task_record(scheduler, prd: str, session_id: str = "", project_name: str = "") -> str:
    """建任务元数据 + 写 IDLE 检查点，返回 task_id。route 与 chat.py 共用，避免重复逻辑。"""
    # P2-1: 内存 dict 加容量上限，超限按插入序淘汰最旧，防长运行泄漏
    # P2-1: 内存 dict 加容量上限防泄漏。
    # P2-5: 淘汰时跳过仍在运行的任务（在 _active_tasks 里），淘汰最旧的非运行记录，
    # 避免误删运行中任务的 prd/元数据导致 /run 拿到空 PRD。
    if len(_task_records) >= _MAX_TASK_RECORDS:
        active = getattr(scheduler, "_active_tasks", {})
        for tid in list(_task_records):
            if tid not in active:
                _task_records.pop(tid, None)
                break
    now = datetime.now(UTC)
    task_id = uuid.uuid4().hex
    _task_records[task_id] = {
        "session_id": session_id,
        "project_name": project_name,
        "created_at": now,
        "prd": prd,
    }
    await scheduler.checkpoint.save(
        task_id,
        CheckpointData(task_id=task_id, state=TaskState.IDLE.value, progress=0.0),
    )
    return task_id


@router.post(
    "",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="创建任务",
    description="提交 PRD 创建任务，写初始 IDLE 检查点。prd 长度 10-5000。",
)
async def create_task(request: Request, req: TaskCreateRequest) -> TaskStatusResponse:
    session_id = ""
    project_name = ""
    if req.session_id:
        session = _session_registry.get(req.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": f"会话 {req.session_id} 不存在",
                    "error_code": "SESSION_NOT_FOUND",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        session_id = session.session_id
        project_name = session.project_name

    # 写记录 + 初始 IDLE 检查点（GET/cancel 据此读真实状态）
    sched = _scheduler(request)
    task_id = await create_task_record(sched, req.prd, session_id, project_name)
    # P2-2: 用记录里的 created_at，保证与后续 GET 一致（避免两个 now 微秒级偏差）
    now = _task_records[task_id]["created_at"]
    return TaskStatusResponse(
        task_id=task_id,
        state=TaskState.IDLE,
        progress=0.0,
        result=None,
        session_id=session_id,
        project_name=project_name,
        created_at=now,
        updated_at=now,
    )


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询任务状态（真实检查点）",
    responses={404: {"model": HTTPExceptionDetail, "description": "任务不存在"}},
)
async def get_task(request: Request, task_id: str) -> TaskStatusResponse:
    sched = _scheduler(request)
    ckpt = await sched.checkpoint.load(task_id)
    if ckpt is None:
        raise _not_found(task_id)
    return _to_response(task_id, ckpt)


@router.post(
    "/{task_id}/run",
    response_model=TaskStatusResponse,
    summary="触发真实后台调度",
    responses={404: {"model": HTTPExceptionDetail, "description": "任务不存在"}},
)
async def run_task_endpoint(request: Request, task_id: str) -> TaskStatusResponse:
    """显式触发任务真实执行——后台 spawn 调度器，可被 cancel 取消。"""
    sched = _scheduler(request)
    ckpt = await sched.checkpoint.load(task_id)
    if ckpt is None:
        raise _not_found(task_id)
    prd = str(_task_records.get(task_id, {}).get("prd", ""))
    sched.spawn_task(task_id, prd)
    return _to_response(task_id, ckpt)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskStatusResponse,
    summary="取消任务（真取消 + CANCELLED 检查点）",
    responses={
        404: {"model": HTTPExceptionDetail, "description": "任务不存在"},
        409: {"model": HTTPExceptionDetail, "description": "任务已终态无法取消"},
    },
)
async def cancel_task(request: Request, task_id: str) -> TaskStatusResponse:
    sched = _scheduler(request)
    ckpt = await sched.checkpoint.load(task_id)
    if ckpt is None:
        raise _not_found(task_id)
    if TaskState(ckpt.state) in _TERMINAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": f"任务 {task_id} 处于终态 {ckpt.state}，无法取消",
                "error_code": "INVALID_STATE",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    await sched.cancel_task(task_id)
    updated = await sched.checkpoint.load(task_id)
    return _to_response(task_id, updated or ckpt)
