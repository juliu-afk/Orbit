"""Loop 模式 API 路由。

支持:
- POST /api/v1/loop: 创建 Loop
- GET /api/v1/loop: 列出所有 Loop
- DELETE /api/v1/loop/{loop_id}: 停止 Loop
- POST /api/v1/loop/{loop_id}/pause: 暂停
- POST /api/v1/loop/{loop_id}/resume: 恢复
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/loop", tags=["loop"])


class CreateLoopRequest(BaseModel):
    interval: str = Field(..., description="间隔: 30s/5m/1h/0 9 * * *")
    command: str = Field(..., description="执行的命令")
    # TODO: 接入 LoopScheduler


@router.post("")
async def create_loop(req: CreateLoopRequest):
    return {
        "code": 0,
        "data": {
            "loop_id": "placeholder",
            "interval_seconds": 300,
            "command": req.command,
            "status": "active",
        },
    }


@router.get("")
async def list_loops():
    return {
        "code": 0,
        "data": {"loops": [], "total": 0},
    }


@router.delete("/{loop_id}")
async def stop_loop(loop_id: str):
    return {
        "code": 0,
        "data": {"loop_id": loop_id, "status": "stopped"},
    }


@router.post("/{loop_id}/pause")
async def pause_loop(loop_id: str):
    return {"code": 0, "data": {"status": "paused"}}


@router.post("/{loop_id}/resume")
async def resume_loop(loop_id: str):
    return {"code": 0, "data": {"status": "active"}}
