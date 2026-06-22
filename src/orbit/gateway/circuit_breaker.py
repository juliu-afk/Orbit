"""熔断器（Step 2.1）。

WHY Redis 存状态：跨实例共享（水平扩展准备），单实例崩溃不丢失熔断计数。
Redis 不可用时降级为内存模式（仅单实例有效，记录警告）。

状态机：
  CLOSED --(连续 N 失败)--> OPEN --(冷却超时)--> HALF_OPEN
  HALF_OPEN --(探测成功)--> CLOSED
  HALF_OPEN --(探测失败)--> OPEN
"""
from __future__ import annotations

import time

import structlog

from orbit.gateway.schemas import CircuitBreakerState

logger = structlog.get_logger()

# 熔断器默认阈值（PRD Step 2.1 SC2/SC3）
DEFAULT_FAILURE_THRESHOLD = 5  # 连续失败 5 次触发
DEFAULT_COoldown = 60  # 冷却 60s（CIRCUIT_BREAKER_TIMEOUT 可覆盖）
DEFAULT_ERROR_RATE_WINDOW = 60  # 1 分钟窗口
DEFAULT_ERROR_RATE_THRESHOLD = 0.30  # 错误率 > 30% 触发
HALF_OPEN_PROBE_LIMIT = 1  # 半开状态放行 1 个探测


class CircuitOpenError(Exception):
    """熔断器打开时抛出，调用方应快速失败不转发请求。"""


class CircuitBreaker:
    """按模型粒度的熔断器（PRD 待定决议 Q2）。

    每个模型一个独立熔断器，key 格式 cb:{model_name}。
    """

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown: int = DEFAULT_COoldown,
        error_rate_threshold: float = DEFAULT_ERROR_RATE_THRESHOLD,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.error_rate_threshold = error_rate_threshold
        # 内存降级模式（Redis 不可用时用）
        self._memory_store: dict[str, CircuitBreakerState] = {}
        self._memory_calls: dict[str, list[bool]] = {}  # key -> [success flags]

    async def before_call(self, key: str) -> None:
        """调用前检查熔断状态。OPEN 或 HALF_OPEN 满则抛 CircuitOpenError。"""
        state = await self._get_state(key)
        now = time.time()
        if state.opened_at is None and not state.half_open:
            return  # CLOSED
        if state.half_open:
            # 半开：只放行第一个探测请求，其他继续拒绝
            logger.warning("circuit_half_open_probe", key=key)
            return
        # OPEN：检查冷却是否到期
        if state.opened_at and (now - state.opened_at) >= self.cooldown:
            # 冷却到期 → 转半开
            state.half_open = True
            state.opened_at = None
            await self._set_state(key, state)
            logger.info("circuit_half_open_entered", key=key)
            return
        # 仍在冷却期
        remaining = int(self.cooldown - (now - (state.opened_at or 0)))
        raise CircuitOpenError(
            f"熔断器开启中（key={key}），{remaining}s 后进入半开探测"
        )

    async def record_success(self, key: str) -> None:
        """记录成功。半开状态下成功 → CLOSED。"""
        state = await self._get_state(key)
        state.failure_count = 0
        state.opened_at = None
        state.half_open = False
        await self._set_state(key, state)
        self._record_call(key, True)

    async def record_failure(self, key: str) -> None:
        """记录失败。达到阈值 → OPEN；半开状态下失败 → 重回 OPEN。"""
        state = await self._get_state(key)
        if state.half_open:
            # 半开失败 → 重新打开
            state.half_open = False
            state.opened_at = time.time()
            await self._set_state(key, state)
            logger.warning("circuit_reopened_after_probe_fail", key=key)
            return
        state.failure_count += 1
        if state.failure_count >= self.failure_threshold:
            state.opened_at = time.time()
            await self._set_state(key, state)
            logger.warning(
                "circuit_opened",
                key=key,
                failures=state.failure_count,
                threshold=self.failure_threshold,
            )
        else:
            await self._set_state(key, state)
        self._record_call(key, False)

    async def get_state(self, key: str) -> CircuitBreakerState:
        """读取熔断器状态（供监控/测试用）。"""
        return await self._get_state(key)

    # ---- Redis / 内存双层（Redis 待 Step 2.2 接入，当前内存优先）----

    async def _get_state(self, key: str) -> CircuitBreakerState:
        # WHY 内存模式：MVP 单实例够用，Step 2.2 Redis 接入后切 Redis。
        # 当前测试用内存，生产切 Redis 跨实例共享。
        return self._memory_store.get(key, CircuitBreakerState())

    async def _set_state(self, key: str, state: CircuitBreakerState) -> None:
        self._memory_store[key] = state

    def _record_call(self, key: str, success: bool) -> None:
        """记录调用结果用于错误率统计。"""
        now = time.time()
        calls = self._memory_calls.setdefault(key, [])
        calls.append(success)
        # 清理窗口外的记录
        self._memory_calls[key] = [s for s in calls if True]  # MVP：保留全部，后续按时间窗口裁剪