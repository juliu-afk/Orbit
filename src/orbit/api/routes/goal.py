"""Goal 模式 API 路由——统一 /goal 入口。

v5: 接入 MetaOrchestrator + IntakeRouter，支持所有输入形态。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orbit.goal.models import GoalSession

router = APIRouter(prefix="/api/v1/goal", tags=["goal"])

_active_task: asyncio.Task | None = None
_active_goal_id: str | None = None


def _on_goal_done(task: asyncio.Task) -> None:
    global _active_task, _active_goal_id
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        import structlog

        structlog.get_logger("orbit.goal").error("goal_background_failed", exc_info=True)
    finally:
        _active_task = None
        _active_goal_id = None


class CreateGoalRequest(BaseModel):
    description: str = Field("", description="目标描述")
    source_file: str = Field("", description="PRD 文件路径")
    source_dir: str = Field("", description="批量目录")
    constraints: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)
    total_budget: int = Field(0)
    max_runtime_seconds: int = Field(0)
    max_parallel_tasks: int = Field(5)
    max_react: int = Field(12)


def _get_orch(request: Request):
    orch = getattr(request.app.state, "meta_orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="MetaOrchestrator 未初始化")
    return orch


@router.post("")
async def create_goal(request: Request, req: CreateGoalRequest):
    """创建 Goal——统一入口。后台异步执行。"""
    global _active_task, _active_goal_id
    orch = _get_orch(request)
    goal = GoalSession(
        description=req.description or req.source_file or req.source_dir,
        constraints=req.constraints,
        verification_commands=req.verification_commands,
        total_token_budget=req.total_budget,
        max_runtime_seconds=req.max_runtime_seconds,
        max_parallel_tasks=req.max_parallel_tasks,
        max_react=req.max_react,
    )
    task = asyncio.create_task(orch.run(goal))
    task.add_done_callback(_on_goal_done)
    _active_task = task
    _active_goal_id = goal.id
    return {
        "code": 0,
        "data": {"goal_id": goal.id, "status": "active", "message": "Goal 已启动"},
    }


@router.get("")
async def get_goal_status(request: Request):
    """GET /api/v1/goal ——查询当前 Goal 状态。"""
    _get_orch(request)
    task = _active_task
    return {
        "code": 0,
        "data": {
            "active": task is not None and not task.done(),
            "goal_id": _active_goal_id,
            "status": "running" if (task and not task.done()) else "idle",
            "sub_tasks": {},
        },
    }


@router.delete("")
async def cancel_goal(request: Request):
    """DELETE /api/v1/goal — /goal clear ——取消当前 Goal。"""
    global _active_task, _active_goal_id
    _get_orch(request)
    task = _active_task
    gid = _active_goal_id
    if task and not task.done():
        task.cancel()
        _active_task = None
        _active_goal_id = None
        return {"code": 0, "data": {"goal_id": gid, "message": "Goal 已取消"}}
    _active_task = None
    _active_goal_id = None
    return {"code": 0, "data": {"message": "无活跃 Goal"}}


@router.post("/pause")
async def pause_goal(request: Request):
    """POST /api/v1/goal/pause ——暂停当前 Goal。"""
    orch = _get_orch(request)
    if not _active_task or _active_task.done():
        return {"code": 0, "data": {"message": "无活跃 Goal 可暂停"}}
    orch.pause()
    return {"code": 0, "data": {"goal_id": _active_goal_id, "status": "paused"}}


@router.post("/resume")
async def resume_goal(request: Request):
    """POST /api/v1/goal/resume ——恢复已暂停的 Goal。"""
    orch = _get_orch(request)
    if not orch.is_paused:
        return {"code": 0, "data": {"message": "Goal 未处于暂停状态"}}
    orch.resume()
    return {"code": 0, "data": {"goal_id": _active_goal_id, "status": "running"}}
