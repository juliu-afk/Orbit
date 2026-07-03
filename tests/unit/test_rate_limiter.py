"""滑动窗口限流器单元测试。

算法：deque 滑动窗口，类级共享 _buckets。
测试覆盖：首次通过、窗口内次数、超限、不同 key 独立、client=None、"unknown" IP、清理。
"""

from __future__ import annotations

import time
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from orbit.api.middleware.rate_limit import RateLimiter, _cleanup_buckets


@pytest.fixture(autouse=True)
def _clear_buckets() -> None:
    """每个测试用例前清理类级桶状态。"""
    RateLimiter._buckets.clear()
    RateLimiter._call_count = 0
    yield


def _mock_request(client_ip: str | None = "127.0.0.1", path: str = "/api/v1/test") -> Mock:
    """创建 mock Request。"""
    req = Mock(spec=Request)
    if client_ip is not None:
        req.client.host = client_ip
    else:
        req.client = None
    req.url.path = path
    return req


class TestRateLimiterCall:
    """RateLimiter.__call__ 方法测试。"""

    @pytest.mark.asyncio
    async def test_first_request_passes(self) -> None:
        """首次请求不触发限流。"""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        await limiter(_mock_request())

    @pytest.mark.asyncio
    async def test_within_limit_passes(self) -> None:
        """窗口内未超限→通过。"""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            await limiter(_mock_request())

    @pytest.mark.asyncio
    async def test_exceeds_limit_raises_429(self) -> None:
        """超限→HTTP 429。"""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        await limiter(_mock_request())
        await limiter(_mock_request())
        with pytest.raises(HTTPException) as exc:
            await limiter(_mock_request())
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_exceed_returns_retry_after_header(self) -> None:
        """超限响应含 Retry-After header。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request())
        with pytest.raises(HTTPException) as exc:
            await limiter(_mock_request())
        assert "Retry-After" in exc.value.headers
        assert int(exc.value.headers["Retry-After"]) >= 1

    @pytest.mark.asyncio
    async def test_different_ips_independent(self) -> None:
        """不同 IP 使用独立桶。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request(client_ip="10.0.0.1"))
        # 不同 IP 应可访问
        await limiter(_mock_request(client_ip="10.0.0.2"))

    @pytest.mark.asyncio
    async def test_different_paths_independent(self) -> None:
        """同一 IP 不同路径使用独立桶。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request(path="/api/v1/path-a"))
        # 不同路径应可访问
        await limiter(_mock_request(path="/api/v1/path-b"))

    @pytest.mark.asyncio
    async def test_same_ip_different_paths(self) -> None:
        """同一 IP 同一路径超限，另一路径不超限。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request(path="/api/v1/limited"))
        with pytest.raises(HTTPException):
            await limiter(_mock_request(path="/api/v1/limited"))
        # 不同路径不超限
        await limiter(_mock_request(path="/api/v1/other"))

    @pytest.mark.asyncio
    async def test_no_client_uses_unknown_ip(self) -> None:
        """client 为 None → 使用 'unknown' 作为 IP。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request(client_ip=None))
        # 'unknown' IP 也超限
        with pytest.raises(HTTPException):
            await limiter(_mock_request(client_ip=None))

    @pytest.mark.asyncio
    async def test_no_client_and_normal_client_different_buckets(self) -> None:
        """无 client 的 'unknown' 与有 client 的不同桶。"""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        await limiter(_mock_request(client_ip=None))  # unknown
        # 有明确 IP 的请求不影响 'unknown' 桶
        await limiter(_mock_request(client_ip="10.0.0.1"))  # different bucket

    @pytest.mark.asyncio
    async def test_window_expiry_allows_new_request(self) -> None:
        """窗口过期后允许新请求。"""
        limiter = RateLimiter(max_requests=1, window_seconds=0.01)
        await limiter(_mock_request())
        with pytest.raises(HTTPException):
            await limiter(_mock_request())
        # 等待窗口过期
        import asyncio
        await asyncio.sleep(0.02)
        await limiter(_mock_request())  # Should pass

    @pytest.mark.asyncio
    async def test_lazy_cleanup_does_not_break(self) -> None:
        """惰性清理计数器增长不破坏功能。"""
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        # 触发清理逻辑：_call_count % _CLEANUP_INTERVAL == 0
        original_count = RateLimiter._call_count
        RateLimiter._call_count = RateLimiter._CLEANUP_INTERVAL - 1
        await limiter(_mock_request())
        assert RateLimiter._call_count == RateLimiter._CLEANUP_INTERVAL


class TestCleanupBuckets:
    """_cleanup_buckets 纯函数测试。"""

    def test_empty_buckets_returns_zero(self) -> None:
        """无桶→清理 0 个。"""
        assert _cleanup_buckets(time.time(), 60) == 0

    def test_removes_expired_bucket(self) -> None:
        """过期桶被移除。"""
        key = "127.0.0.1:/test"
        RateLimiter._buckets[key].append(time.time() - 120)  # 2 分钟前→过期
        assert _cleanup_buckets(time.time(), 60) == 1
        assert key not in RateLimiter._buckets

    def test_keeps_active_bucket(self) -> None:
        """未过期桶保留。"""
        key = "active:/test"
        RateLimiter._buckets[key].append(time.time())
        assert _cleanup_buckets(time.time(), 60) == 0
        assert key in RateLimiter._buckets

    def test_cleans_expired_and_keeps_active(self) -> None:
        """混合场景：清除过期的，保留未过期的。"""
        expired = "expired:/old"
        active = "active:/new"
        RateLimiter._buckets[expired].append(time.time() - 120)
        RateLimiter._buckets[active].append(time.time())
        assert _cleanup_buckets(time.time(), 60) == 1
        assert expired not in RateLimiter._buckets
        assert active in RateLimiter._buckets

    def test_cleans_partially_expired_bucket(self) -> None:
        """桶内部分过期记录移除但桶保留。"""
        key = "mixed:/test"
        RateLimiter._buckets[key].append(time.time() - 120)  # 过期
        RateLimiter._buckets[key].append(time.time())  # 未过期
        assert _cleanup_buckets(time.time(), 60) == 0  # 桶仍有内容→未删除
        assert len(RateLimiter._buckets[key]) == 1  # 只剩未过期的
