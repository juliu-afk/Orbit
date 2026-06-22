"""健康检查路由（Step 1.1 AC1：/health 返回 status=ok）。"""

from __future__ import annotations

from fastapi import APIRouter

from orbit.api.schemas.task import HealthResponse

# WHY 版本号集中管理：避免散落多处，发版时只改一处。
# 读自 importlib.metadata（打包后生效），fallback 到硬编码（开发态）。
try:
    from importlib.metadata import version as _pkg_version

    _APP_VERSION = _pkg_version("orbit")
except Exception:  # noqa: BLE001 - 开发态未装包时 fallback
    _APP_VERSION = "0.1.0"

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=_APP_VERSION)
