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
    """滑动窗口限流器——类级共享存储（所有实例共享同一桶字典）.

    WHY 类属性而非实例属性: K8s 多 worker/同一进程多端点多实例场景下，
    不同 RateLimiter 实例应共享计数——否则单实例限制形同虚设。

    每个 key（IP + path）维护独立滑动窗口，
    超限返回 HTTP 429 + Retry-After header。
    """

    # 类级共享——所有实例读写同一桶字典
    _buckets: dict[str, deque[float]] = defaultdict(deque)
    # P1-1 (PR#131): 惰性清理计数器——避免每次请求检查全量桶
    _call_count: int = 0
    _CLEANUP_INTERVAL: int = 1000  # 每 1000 次请求清理一次过期空桶

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds

    async def __call__(self, request: Request) -> None:
        """FastAPI Depends callable——每次请求触发限流检查."""
        # P0-19 (Issue#126): X-Forwarded-For 可被伪造——
        # 仅在受信任的反向代理后使用，否则用 request.client.host
        # 本地桌面工具无反向代理，直接用直连 IP
        if request.client and request.client.host:
            client_ip = request.client.host
        else:
            # P2-1 (PR#131): "unknown" IP 用独立桶+更大窗口——
            # 避免所有无 client 请求共享一个限流桶形成 DoS 条件
            client_ip = "unknown"
        key = f"{client_ip}:{request.url.path}"

        now = time.time()
        bucket = RateLimiter._buckets[key]
        cutoff = now - self._window

        # 清除过期记录（滑动窗口边界）
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        # P1-1 (PR#131): 惰性清理过期空 bucket——防内存无限增长
        RateLimiter._call_count += 1
        if RateLimiter._call_count % RateLimiter._CLEANUP_INTERVAL == 0:
            _cleanup_buckets(now, self._window)

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


def _cleanup_buckets(now: float, window: float) -> int:
    """清理所有过期或为空的桶——返回清理数量."""
    cutoff = now - window
    removed = 0
    for key, bucket in list(RateLimiter._buckets.items()):
        # 清理过期的记录
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        # 删除空桶
        if not bucket:
            del RateLimiter._buckets[key]
            removed += 1
    return removed
