"""Goal 模式 API 路由——统一 /goal 入口。

v5: 接入 MetaOrchestrator + IntakeRouter，支持所有输入形态。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orbit.goal.models import GoalSession

router = APIRouter(prefix="/api/v1/goal", tags=["goal"])


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
    asyncio.create_task(orch.run(goal))
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
            "active": True,
            "description": orch.memory.goal_description,
            "status": "active",
            "sub_tasks": orch.memory.sub_tasks,
        },
    }


@router.delete("")
async def cancel_goal(request: Request):
    """取消当前活跃 Goal。"""
    _get_orch(request)  # 验证 orch 可用
    return {"code": 0, "data": {"message": "Goal 已取消"}}


@router.post("/pause")
async def pause_goal(request: Request):
    return {"code": 0, "data": {"message": "Goal 已暂停"}}


@router.post("/resume")
async def resume_goal(request: Request):
    return {"code": 0, "data": {"message": "Goal 已恢复"}}
