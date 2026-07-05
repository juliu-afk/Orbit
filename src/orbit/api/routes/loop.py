"""Loop 模式 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/loop", tags=["loop"])


class CreateLoopRequest(BaseModel):
    # P2-5: interval 格式校验——数字+单位或 cron 5字段
    interval: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^(\d+\s*(s|sec|second|m|min|minute|h|hr|hour|d|day)|hourly|daily|weekly|[\d\*/,]+\s+[\d\*/,]+\s+[\d\*/,]+\s+[\d\*/,]+\s+[\d\*/,]+)$",
        description="30s/5m/1h/hourly/daily/0 9 * * *",
    )
    command: str = Field(..., min_length=1)


def _get_scheduler(request: Request):
    sched = getattr(request.app.state, "loop_scheduler", None)
    if sched is None:
        raise HTTPException(status_code=503, detail="LoopScheduler 未初始化")
    return sched


@router.post("")
async def create_loop(request: Request, req: CreateLoopRequest):
    sched = _get_scheduler(request)
    loop = await sched.create(req.interval, req.command)
    await sched.start(loop.id)
    return {
        "code": 0,
        "data": {
            "loop_id": loop.id,
            "interval_seconds": loop.interval_seconds,
            "command": loop.command,
            "status": loop.status,
        },
    }


@router.get("")
async def list_loops(request: Request):
    sched = _get_scheduler(request)
    loops = sched.list_all()
    return {
        "code": 0,
        "data": {
            "loops": [
                {
                    "id": l.id,
                    "interval_seconds": l.interval_seconds,
                    "command": l.command,
                    "status": l.status,
                    "run_count": l.run_count,
                }
                for l in loops
            ],
            "total": len(loops),
        },
    }


@router.delete("/{loop_id}")
async def stop_loop(request: Request, loop_id: str):
    await _get_scheduler(request).stop(loop_id)
    return {"code": 0, "data": {"loop_id": loop_id, "status": "stopped"}}


@router.post("/{loop_id}/pause")
async def pause_loop(request: Request, loop_id: str):
    await _get_scheduler(request).pause(loop_id)
    return {"code": 0, "data": {"status": "paused"}}


@router.post("/{loop_id}/resume")
async def resume_loop(request: Request, loop_id: str):
    await _get_scheduler(request).resume(loop_id)
    return {"code": 0, "data": {"status": "active"}}
