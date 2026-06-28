"""/dream API 端点——记忆合并自循环入口 (Phase 2 AC10).

WHY 独立路由: DreamEngine 已实现但无 HTTP 入口，前端/BFF 无法触发。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from orbit.dream.engine import DreamEngine
from orbit.dream.models import DreamConfig, DreamResult

router = APIRouter()


class DreamRunRequest(BaseModel):
    """触发 dream 循环请求."""

    config: DreamConfig | None = Field(None, description="合并配置——不传用默认值")


class DreamStatusResponse(BaseModel):
    status: str
    result: DreamResult | None = None
    message: str = ""


@router.post("/dream/run")
async def dream_run(request: Request, body: DreamRunRequest) -> dict[str, Any]:
    """执行 dream 循环——5 阶段记忆合并（GATHER→MERGE_1→MERGE_2→DEDUP→VERIFY）。

    无 LLM 配置时 MERGE 阶段退化为纯文本去重合并。
    """
    engine: DreamEngine | None = getattr(request.app.state, "dream_engine", None)
    if engine is None:
        return {"code": 500, "data": None, "message": "DreamEngine 未配置"}
    # 如果请求携带自定义 config，应用后运行
    if body.config:
        engine._config = body.config
    result = await engine.run()
    return {"code": 0, "data": result.model_dump(), "message": "ok"}


@router.get("/dream/status")
async def dream_status(request: Request) -> dict[str, Any]:
    """查询 dream 引擎状态（健康检查）。"""
    engine: DreamEngine | None = getattr(request.app.state, "dream_engine", None)
    if engine is None:
        return {"code": 0, "data": {"status": "not_configured"}, "message": "ok"}
    return {
        "code": 0,
        "data": {
            "status": "ready",
            "config": engine._config.model_dump() if engine._config else None,
        },
        "message": "ok",
    }
