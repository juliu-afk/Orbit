"""高峰避让调度 API 路由。

端点:
- GET  /api/v1/schedule/peak-status    — 查询当前高峰状态
- GET  /api/v1/schedule/queue           — 查询延迟队列
- POST /api/v1/schedule/queue/{id}/urgent — 提升任务为紧急执行
- GET  /api/v1/schedule/savings-report  — 成本节省报告
- POST /api/v1/schedule/reload-config   — 热重载配置
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])


# ── 辅助 ──

def _get_offpeak(request: Request):
    """获取 OffPeakScheduler——挂载在 app.state。"""
    offpeak = getattr(request.app.state, "offpeak_scheduler", None)
    if offpeak is None:
        raise HTTPException(status_code=503, detail="OffPeakScheduler 未初始化")
    return offpeak


# ── GET /peak-status ──────────────────────────────────────────

@router.get("/peak-status")
async def get_peak_status(request: Request):
    """查询所有厂商的当前高峰状态 + 队列摘要。"""
    offpeak = _get_offpeak(request)
    peak_mgr: PeakWindowManager = offpeak.peak_manager
    queue = offpeak.queue

    provider_status = peak_mgr.get_all_status()
    queued = await queue.list_all("queued")

    by_provider: dict[str, int] = {}
    for t in queued:
        by_provider[t.provider] = by_provider.get(t.provider, 0) + 1

    # 转换为可 JSON 序列化的格式
    providers_dict: dict[str, dict[str, Any]] = {}
    is_any_peak = False
    for name, status in provider_status.items():
        providers_dict[name] = {
            "is_peak": status.is_peak,
            "peak_ends_at": status.peak_ends_at,
            "next_offpeak": {
                "starts_at": status.next_offpeak_starts_at,
                "ends_at": status.next_offpeak_ends_at,
            } if status.next_offpeak_starts_at else None,
        }
        if status.is_peak:
            is_any_peak = True

    return {
        "code": 0,
        "data": {
            "is_peak": is_any_peak,
            "providers": providers_dict,
            "queue_summary": {
                "total_queued": len(queued),
                "by_provider": by_provider,
            },
        },
    }


# ── GET /queue ─────────────────────────────────────────────────

@router.get("/queue")
async def get_queue(request: Request):
    """查询当前延迟队列。"""
    offpeak = _get_offpeak(request)
    queue = offpeak.queue
    tasks = await queue.list_all("queued")
    return {
        "code": 0,
        "data": {
            "queued": [
                {
                    "goal_id": t.id,
                    "description": t.goal_description,
                    "priority": t.priority,
                    "provider": t.provider,
                    "target_window_start": t.target_window_start,
                    "estimated_duration_seconds": t.estimated_duration_seconds,
                    "status": t.status,
                }
                for t in tasks
            ],
            "count": len(tasks),
        },
    }


# ── POST /queue/{goal_id}/urgent ───────────────────────────────

@router.post("/queue/{goal_id}/urgent")
async def promote_to_urgent(request: Request, goal_id: str):
    """将排队任务提升为立即执行——忽略高峰限制。

    返回 404 如果任务不在队列，409 如果任务已在执行。
    """
    offpeak = _get_offpeak(request)
    queue = offpeak.queue

    task = await queue.promote_to_urgent(goal_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {goal_id} 不在排队队列中或已释放")

    # 立即执行
    from orbit.goal.models import GoalSession
    goal = GoalSession.model_validate_json(task.goal_json)

    async def _on_urgent_done(t: asyncio.Task) -> None:
        try: t.result()
        except Exception: pass

    bg = asyncio.create_task(offpeak.orchestrator.run(goal))
    bg.add_done_callback(lambda t: asyncio.ensure_future(_on_urgent_done(t)))

    return {
        "code": 0,
        "data": {
            "goal_id": goal_id,
            "status": "urgent_released",
            "message": "任务已提升为紧急执行",
        },
    }


# ── GET /savings-report ────────────────────────────────────────

@router.get("/savings-report")
async def get_savings_report(request: Request):
    """成本节省报告。"""
    offpeak = _get_offpeak(request)
    queue = offpeak.queue
    report = await queue.get_savings_report()
    return {"code": 0, "data": report}


# ── POST /reload-config ────────────────────────────────────────

@router.post("/reload-config")
async def reload_config(request: Request) -> dict[str, Any]:
    """热重载高峰时段配置 + 节假日数据。"""
    offpeak = _get_offpeak(request)
    peak_mgr = offpeak.peak_manager
    peak_mgr.reload()
    return {
        "code": 0,
        "data": {
            "status": "ok",
            "providers": peak_mgr.providers,
            "message": "配置已重新加载",
        },
    }
