"""Goal 模式 API 路由——统一 /goal 入口。

支持:
- POST /api/v1/goal: 创建 Goal（模糊需求/PRD文件/批量目录）
- GET /api/v1/goal: 查询 Goal 状态
- DELETE /api/v1/goal: 取消 Goal
- POST /api/v1/goal/pause: 暂停
- POST /api/v1/goal/resume: 恢复
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/goal", tags=["goal"])


# ── Request/Response 模型 ────────────────────────────

class CreateGoalRequest(BaseModel):
    """创建 Goal 请求——支持多种输入形态。"""
    description: str = Field("", description="目标描述（模糊需求）")
    source_file: str = Field("", description="单个 PRD 文件路径")
    source_dir: str = Field("", description="批量目录路径")
    constraints: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)
    total_budget: int = Field(0, description="Token 配额，0=无限制")
    max_runtime_seconds: int = Field(0, description="时间上限，0=无限制")
    max_parallel_tasks: int = Field(5)
    max_react: int = Field(12)


class GoalStatusResponse(BaseModel):
    """Goal 状态响应。"""
    active: bool = False
    description: str = ""
    status: str = "idle"
    react_count: int = 0
    max_react: int = 12
    sub_tasks: dict[str, str] = Field(default_factory=dict)
    token_consumed: int = 0
    total_token_budget: int = 0
    last_verdict: dict | None = None


# ── 端点 ─────────────────────────────────────────────

@router.post("")
async def create_goal(req: CreateGoalRequest):
    """创建 Goal——统一入口。

    输入形态自动判定:
    - description 非空: 模糊需求模式
    - source_file 非空: 单文件模式
    - source_dir 非空: 批量模式
    """
    # TODO: 接入 MetaOrchestrator
    return {
        "code": 0,
        "data": {
            "goal_id": "placeholder",
            "status": "active",
            "message": "Goal 创建成功（占位——MetaOrchestrator 接入中）",
        },
    }


@router.get("")
async def get_goal_status():
    """查询当前活跃 Goal 状态。"""
    # TODO: 从 goal_sessions 表读取
    return {
        "code": 0,
        "data": GoalStatusResponse().model_dump(),
    }


@router.delete("")
async def cancel_goal():
    """取消当前活跃 Goal。"""
    # TODO: 发送取消信号 → MetaOrchestrator
    return {
        "code": 0,
        "data": {"message": "Goal 已取消"},
    }


@router.post("/pause")
async def pause_goal():
    """暂停 Goal 执行。"""
    return {
        "code": 0,
        "data": {"message": "Goal 已暂停"},
    }


@router.post("/resume")
async def resume_goal():
    """恢复 Goal 执行。"""
    return {
        "code": 0,
        "data": {"message": "Goal 已恢复"},
    }
