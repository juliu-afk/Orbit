"""Compose API 端点——spec-driven 多 Agent 编排入口 (Phase 4 AC-A7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter()


class ComposeRunRequest(BaseModel):
    spec: str = Field(..., min_length=1, description="spec YAML 文本")


@router.post("/compose/run")
async def compose_run(request: Request, body: ComposeRunRequest) -> dict[str, Any]:
    """执行 spec——完整编排流程。"""
    orch = getattr(request.app.state, "compose_orchestrator", None)
    if orch is None:
        return {"code": 500, "data": None, "message": "ComposeOrchestrator 未配置"}
    result = await orch.run_spec(body.spec)
    return {"code": 0, "data": result, "message": "ok"}
