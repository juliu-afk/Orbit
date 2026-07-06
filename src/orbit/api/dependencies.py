"""API 依赖项——token认证 + SSE流式token (5C.1) + JWT (P1-3).

WHY 统一认证中间件: 审计 Issue #126 发现整个API层无鉴权，
配合 CORS allow_origins=["*"] 构成本地RCE攻击链。
中间件在请求到达路由前验证 X-Orbit-Token header。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Query, Request
from starlette.middleware.base import BaseHTTPMiddleware

from orbit.core.config import settings

# ── JWT 支持 (P1-3) ──
# WHY 条件导入: PyJWT 可能未安装（精简部署），降级到静态 token
try:
    import jwt as _jwt

    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False


def create_jwt_token(user: str = "orbit-user", ttl_minutes: int | None = None) -> str:
    """生成 JWT——有效期默认 settings.JWT_TTL_MINUTES 分钟。

    P1-3: 替代静态 token，支持过期和轮换。
    PyJWT 不可用时抛 ImportError。
    """
    if not _HAS_JWT:
        raise ImportError("PyJWT 未安装——无法生成 JWT token")
    ttl = ttl_minutes if ttl_minutes is not None else settings.JWT_TTL_MINUTES
    payload = {
        "sub": user,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl),
    }
    return _jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_jwt_token(token: str) -> dict:
    """验证 JWT——返回 payload，无效时抛异常。"""
    if not _HAS_JWT:
        raise ImportError("PyJWT 未安装——无法验证 JWT token")
    return _jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def _verify_token(token: str) -> bool:
    """统一 token 验证——静态 token 优先，JWT 降级。

    P1-3: 双模式——静态 token 用于开发/桌面，JWT 用于生产分布式部署。
    """
    if not token:
        return False
    # 静态 token 优先（向后兼容）
    if token == settings.ORBIT_AUTH_TOKEN:
        return True
    # JWT 验证
    if _HAS_JWT:
        try:
            verify_jwt_token(token)
            return True
        except Exception:
            pass
    return False


# ── SSE 流式 token —— P1-1: Header 优先，Query 降级 ──
# WHY Header 优先: 防止 token 泄露到 URL/日志/浏览器历史/Referer
# WHY Query 降级: 原生 EventSource 不支持自定义 Header，向后兼容


def verify_stream_token(
    token_header: str | None = Header(None, alias="X-Orbit-Token"),
    token_query: str | None = Query(None, alias="token"),
) -> str:
    """SSE token认证——Header 优先，Query 降级。

    P1-1: token 经 HTTP Header 传递避免 URL 泄露。
    保留 Query fallback 向后兼容旧客户端。
    """
    actual = token_header or token_query
    if not actual or not _verify_token(actual):
        raise HTTPException(status_code=403, detail="token 无效")
    return actual


# ── 公开路径 —— 无需认证 ──
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
     "/api/v1/wechat/callback"}  # iLink 回调无需 Orbit auth token
)


def _is_public_path(path: str) -> bool:
    """检查路径是否为公开端点（无需认证）."""
    # 精确匹配
    if path in _PUBLIC_PATHS:
        return True
    # 前缀匹配：/assets（含无尾部斜杠）和文档路径
    if path.startswith("/assets") or path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """统一鉴权中间件——验证 X-Orbit-Token header。

    WHY BaseHTTPMiddleware: Starlette 中间件在路由匹配前执行，
    确保所有端点（包括 websocket、SSE）统一受保护。

    公开路径（/health、/metrics、/docs 等）跳过验证。

    P1-3: 支持静态 token + JWT 双模式验证。
    """

    async def dispatch(self, request: Request, call_next):
        # 公开路径放行
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 验证 X-Orbit-Token（P1-3: 静态 token + JWT 双模式）
        token = request.headers.get("X-Orbit-Token", "")
        if not _verify_token(token):
            # P0-1: 安全——不泄露预期token格式
            # P2-6: 认证失败记录日志
            import structlog as _sl
            _sl.get_logger("orbit.auth").warning(
                "auth_failed",
                path=request.url.path,
                client=request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=401, detail="未授权访问")

        return await call_next(request)
