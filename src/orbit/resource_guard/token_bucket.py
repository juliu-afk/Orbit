"""令牌桶算法 (Step 7.3 ResourceGuard).

WHY 令牌桶而非固定窗口:
- 固定窗口边界处会双倍放行 (12:00:59 和 12:01:00 各满额)
- 令牌桶允许突发但限制长期平均速率, 更平滑
- O(1) 时间, 纯内存, 无锁 (单线程 asyncio)

算法:
- 桶容量 capacity, 速率 rate (令牌/秒)
- 每次 allow(n): 补充令牌 (按时间流逝) → 扣减 n → 够则 True
"""

from __future__ import annotations

import time


class TokenBucket:
    """令牌桶——全局 LLM Token 消耗限速。

    用法:
        bucket = TokenBucket(capacity=100000, rate=5000)  # 10万容量, 5k/秒
        if bucket.allow(500):  # 请求 500 token
            ...  # 放行
        else:
            ...  # 限流
    """

    def __init__(self, capacity: float, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate  # 令牌/秒
        self._tokens = capacity  # 当前令牌数
        self._last_refill = time.monotonic()  # 上次补充时间

    def allow(self, tokens: float = 1.0) -> bool:
        """请求 tokens 个令牌。够则扣减并返回 True，否则 False。

        不阻塞——调用方根据返回值决定放行还是降级。
        P99 目标 <12ms (纯内存计算)。
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """按时间流逝补充令牌。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        """当前可用令牌数（只读）。"""
        self._refill()
        return self._tokens

    def reset(self) -> None:
        """重置为满桶（测试用）。"""
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
