"""Goal 模式 API 路由——统一 /goal 入口。

v5: 接入 MetaOrchestrator + IntakeRouter，支持所有输入形态。
Phase 3 组 2: pause/resume 实现——asyncio.Event 控制流暂停。
"""

from __future__ import annotations

import asyncio
import os
import structlog

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from orbit.core.config import settings
from orbit.goal.models import GoalSession

router = APIRouter(prefix="/api/v1/goal", tags=["goal"])

# 活跃 Goal 的 task 引用——供 cancel/pause/resume
_active_task: asyncio.Task | None = None
_active_goal_id: str | None = None


def _on_goal_done(task: asyncio.Task) -> None:
    """P1-2: Goal 任务完成/异常回调——清理活跃引用。"""
    global _active_task, _active_goal_id
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        structlog.get_logger("orbit.goal").error("goal_background_task_failed", exc_info=True)
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
    # D13: 高峰避让延迟调度
    defer_to_offpeak: bool = Field(False, description="延迟到低峰执行")
    urgent: bool = Field(False, description="紧急任务——忽略高峰限制立即执行")
    target_provider: str = Field("", description="目标 LLM 厂商（deepseek/anthropic/openai/glm）")
    max_price_multiplier: float = Field(0.0, ge=0.0, description="最高价格倍数，0=不限")


def _get_orch(request: Request):
    orch = getattr(request.app.state, "meta_orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="MetaOrchestrator 未初始化")
    return orch


@router.post("")
async def create_goal(request: Request, req: CreateGoalRequest):
    """创建 Goal——统一入口。后台异步执行。

    P1 ERR-2: 校验 workspace 存在——未初始化时下游子任务静默失败。
    P1-1 (#152): 并发冲突保护——已存在活跃 Goal 时返回 409。
    """
    global _active_task, _active_goal_id
    if _active_task and not _active_task.done():
        raise HTTPException(
            status_code=409,
            detail=f"已有活跃 Goal ({_active_goal_id})，请先取消再创建",
        )
    _ws = settings.WORKSPACE_DIR or os.getcwd()
    if not os.path.isdir(_ws):
        raise HTTPException(status_code=400, detail=f"工作目录不存在: {_ws}")
    orch = _get_orch(request)
    goal = GoalSession(
        description=req.description or req.source_file or req.source_dir,
        constraints=req.constraints,
        verification_commands=req.verification_commands,
        total_token_budget=req.total_budget,
        max_runtime_seconds=req.max_runtime_seconds,
        max_parallel_tasks=req.max_parallel_tasks,
        max_react=req.max_react,
        # D13: 高峰避让
        defer_to_offpeak=req.defer_to_offpeak,
        urgent=req.urgent,
        target_provider=req.target_provider,
        max_price_multiplier=req.max_price_multiplier,
    )

    # D13: 高峰自动询问——未设 defer/urgent 且当前为高峰时提示用户选择
    if not req.defer_to_offpeak and not req.urgent:
        offpeak = getattr(request.app.state, "offpeak_scheduler", None)
        if offpeak is not None:
            provider = req.target_provider or "deepseek"
            if offpeak.peak_manager.is_peak(provider):
                next_window = offpeak.peak_manager.next_offpeak_window(provider)
                next_start = getattr(next_window, "starts_at_iso", "") if next_window else ""
                return {
                    "code": 0,
                    "data": {
                        "goal_id": goal.id,
                        "status": "peak_prompt",
                        "provider": provider,
                        "next_offpeak": next_start,
                        "prompt": (
                            f"当前为 {provider} 高峰期。"
                            f"是否延迟到低峰窗口执行（{next_start}）？"
                            "设置 defer_to_offpeak=true 延迟执行，"
                            "或设置 urgent=true 立即执行。"
                        ),
                    },
                    "message": f"高峰期——请选择 defer_to_offpeak 或 urgent",
                }

    # D13: 延迟执行分支——OffPeakScheduler 拦截
    if req.defer_to_offpeak and not req.urgent:
        offpeak = getattr(request.app.state, "offpeak_scheduler", None)
        if offpeak is None:
            raise HTTPException(status_code=503, detail="OffPeakScheduler 未初始化")
        enqueue_result = await offpeak.enqueue(goal)
        if enqueue_result.status == "peak_warning":
            raise HTTPException(
                status_code=409,
                detail=enqueue_result.warning_message,
            )
        return {
            "code": 0,
            "data": {
                "goal_id": goal.id,
                "status": "queued",
                "target_window_start": enqueue_result.target_window_start,
                "target_window_end": enqueue_result.target_window_end,
                "queue_position": enqueue_result.queue_position,
            },
            "message": "任务已排队到低峰窗口",
        }

    # P1-2: fire-and-forget + 异常回调（现有路径——立即执行）
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
    """POST /api/v1/goal/pause ——暂停当前 Goal。

    WHY asyncio.Event: MetaOrchestrator 在层间检查 _pause_event.wait()，
    clear() 后循环阻塞，set() 后继续。
    """
    orch = _get_orch(request)
    if not _active_task or _active_task.done():
        return {"code": 0, "data": {"message": "无活跃 Goal 可暂停"}}
    orch.pause()
    return {"code": 0, "data": {"goal_id": _active_goal_id, "status": "paused"}}


@router.post("/resume")
async def resume_goal(request: Request):
    """POST /api/v1/goal/resume ——恢复已暂停的 Goal。

    P2-1: 先检查活跃任务，再检查暂停状态——客户端可区分"已完成"和"从未暂停"。
    """
    orch = _get_orch(request)
    if not _active_task or _active_task.done():
        return {"code": 0, "data": {"message": "无活跃 Goal"}}
    if not orch.is_paused:
        return {"code": 0, "data": {"message": "Goal 未处于暂停状态"}}
    orch.resume()
    return {"code": 0, "data": {"goal_id": _active_goal_id, "status": "running"}}
