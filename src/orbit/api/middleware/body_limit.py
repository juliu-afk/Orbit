"""请求体大小限制中间件 (P2-7).

WHY 限制请求体: 防止恶意超大请求耗尽内存。
Starlette 无内置请求体大小限制，需自定义中间件。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

# 默认 10MB——生产环境可按需调整
DEFAULT_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """拒绝超过 max_bytes 的请求体——返回 413。

    用法:
        app.add_middleware(BodySizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
    """

    def __init__(self, app, max_bytes: int = DEFAULT_MAX_BODY_SIZE) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "code": 413,
                            "data": None,
                            "message": f"请求体过大 ({length} bytes)，"
                            f"上限 {self.max_bytes} bytes",
                        },
                    )
            except ValueError:
                pass  # 非法的 content-length，交给下游处理
        return await call_next(request)
