"""API 层限流依赖——滑动窗口速率限制.

WHY 独立中间件: Compose/Agent 等重量端点需要防滥用，但不需要 Redis 依赖（MVP）。
算法：deque 滑动窗口，复用 ToolRegistry._check_rate_limit 模式。

Usage:
    _compose_limiter = RateLimiter(max_requests=5, window_seconds=60)

    @router.post("/compose/run")
    async def compose_run(_: None = Depends(_compose_limiter)):
        ...
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    """滑动窗口限流器——内存存储，重启清零（MVP 可接受）.

    每个 key（IP + path）维护独立滑动窗口，
    超限返回 HTTP 429 + Retry-After header。
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        """FastAPI Depends callable——每次请求触发限流检查."""
        # 客户端标识——X-Forwarded-For 优先（反向代理后真实 IP）
        client_ip = request.headers.get(
            "X-Forwarded-For",
            request.client.host if request.client else "unknown",
        )
        key = f"{client_ip}:{request.url.path}"

        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - self._window

        # 清除过期记录（滑动窗口边界）
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self._max:
            # 计算多久后可重试
            retry_after = int(bucket[0] + self._window - now) if bucket else self._window
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "请求过于频繁，请稍后重试",
                    "retry_after_seconds": max(1, retry_after),
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        bucket.append(now)
