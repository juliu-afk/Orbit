"""API 依赖项——token认证 + SSE流式token (5C.1).

WHY 统一认证中间件: 审计 Issue #126 发现整个API层无鉴权，
配合 CORS allow_origins=["*"] 构成本地RCE攻击链。
中间件在请求到达路由前验证 X-Orbit-Token header。
"""

from __future__ import annotations

from fastapi import HTTPException, Query, Request
from starlette.middleware.base import BaseHTTPMiddleware

from orbit.core.config import settings

# ── SSE 流式 token —— 从环境变量读取，禁止硬编码 ──
# WHY 环境变量: Issue #126 P0-3——硬编码 "orbit-local-stream" 漏洞
# P2-2 (PR#130): 直接读 settings.ORBIT_AUTH_TOKEN 而非模块级缓存——
# 避免未来 Settings 热加载时 token 不同步


def verify_stream_token(token: str = Query(...)) -> str:
    """SSE token认证——从环境变量读取，每次启动随机生成."""
    if token != settings.ORBIT_AUTH_TOKEN:
        raise HTTPException(status_code=403, detail="token 无效")
    return token


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
    # P1-7 (PR#130): /assets 根路径不匹配 startswith("/assets/")——
    # app.mount("/assets", ...) 的 301 重定向请求会被鉴权拦截
    if path.startswith("/assets") or path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """统一鉴权中间件——验证 X-Orbit-Token header.

    WHY BaseHTTPMiddleware: Starlette 中间件在路由匹配前执行，
    确保所有端点（包括 websocket、SSE）统一受保护。

    公开路径（/health、/metrics、/docs 等）跳过验证。
    """

    async def dispatch(self, request: Request, call_next):
        # 公开路径放行
        # P2-1 (PR#130): OPTIONS 分支已移除——Starlette 中间件 LIFO 执行顺序，
        # CORSMiddleware 在内层先处理 OPTIONS 并返回，不会到达 AuthMiddleware
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 验证 X-Orbit-Token
        token = request.headers.get("X-Orbit-Token", "")
        if token != settings.ORBIT_AUTH_TOKEN:
            # P0-1: 安全——不泄露预期token格式
            raise HTTPException(status_code=401, detail="未授权访问")

        return await call_next(request)
