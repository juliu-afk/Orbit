"""Goal 模式 API 路由——统一 /goal 入口。

v5: 接入 MetaOrchestrator + IntakeRouter，支持所有输入形态。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orbit.goal.models import GoalSession

router = APIRouter(prefix="/api/v1/goal", tags=["goal"])

# 活跃 Goal 的 task 引用——供 cancel/pause/resume
_active_task: asyncio.Task | None = None
_active_goal_id: str | None = None


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


def _on_goal_done(task: asyncio.Task) -> None:
    """P1-2: Goal 任务完成/异常回调。"""
    global _active_task, _active_goal_id
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        import structlog

        logger = structlog.get_logger("orbit.goal")
        logger.error("goal_background_task_failed", exc_info=True)
    finally:
        _active_task = None
        _active_goal_id = None


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
    # P1-2: fire-and-forget + 异常回调
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
    """查询当前活跃 Goal 状态。"""
    orch = _get_orch(request)
    return {
        "code": 0,
        "data": {
            "active": _active_task is not None,
            "goal_id": _active_goal_id,
            "description": orch.memory.goal_description,
            "status": "active" if _active_task else "idle",
            "sub_tasks": orch.memory.sub_tasks,
        },
    }


@router.delete("")
async def cancel_goal(request: Request):
    """P1-3: 取消当前活跃 Goal——发送取消信号。"""
    _get_orch(request)
    global _active_task, _active_goal_id
    if _active_task and not _active_task.done():
        _active_task.cancel()
        cancelled_id = _active_goal_id
        _active_task = None
        _active_goal_id = None
        return {"code": 0, "data": {"goal_id": cancelled_id, "message": "Goal 已取消"}}
    return {"code": 0, "data": {"message": "无活跃 Goal"}}


@router.post("/pause")
async def pause_goal(request: Request):
    """P1-3: 暂停——orchestrator 暂不支持，返回 501。"""
    _get_orch(request)
    raise HTTPException(status_code=501, detail="Goal pause/resume 功能待实现")


@router.post("/resume")
async def resume_goal(request: Request):
    """P1-3: 恢复——orchestrator 暂不支持，返回 501。"""
    _get_orch(request)
    raise HTTPException(status_code=501, detail="Goal pause/resume 功能待实现")
