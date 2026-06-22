"""健康检查路由（Step 1.1 AC1：/health 返回 status=ok）。"""
from __future__ import annotations

from fastapi import APIRouter

from orbit.api.schemas.task import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")