"""健康检查路由（Step 1.1 AC1：/health 返回状态）。"""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from orbit.api.schemas.task import HealthResponse
from orbit.core.config import settings

# P2-1 (PR#138): redis 可选依赖提到模块顶部
try:
    import redis.asyncio as aioredis

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

logger = structlog.get_logger("orbit.health")

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
    """健康检查——P1 ERR-1: 验证 Redis 连通性，不再始终假绿。"""
    status = "ok"
    if not _REDIS_AVAILABLE:
        status = "degraded"
        logger.warning("health_redis_not_installed")
    else:
        # P1-1 (PR#138): try-finally 确保连接关闭，防止泄漏
        try:
            _redis = aioredis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
            )
            try:
                await _redis.ping()
            finally:
                await _redis.close()
        except Exception:
            status = "degraded"
            logger.warning("health_redis_unavailable")

    return HealthResponse(status=status, version=_APP_VERSION)
