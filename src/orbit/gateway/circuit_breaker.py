"""熔断器（Step 2.1）。

WHY Redis 存状态：跨实例共享（水平扩展准备），单实例崩溃不丢失熔断计数。
Redis 不可用时降级为内存模式（仅单实例有效，记录警告）。

状态机：
  CLOSED --(连续 N 失败 或 错误率超阈值)--> OPEN --(冷却超时)--> HALF_OPEN
  HALF_OPEN --(探测成功)--> CLOSED
  HALF_OPEN --(探测失败)--> OPEN

熔断触发条件（PRD Step 2.1）：
  ① 连续 failure_threshold 次失败（默认 5）
  ② 错误率窗口内（默认 60s）错误率 > error_rate_threshold（默认 30%）
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

import structlog

from orbit.gateway.schemas import CircuitBreakerState

logger = structlog.get_logger()

# 熔断器默认阈值（PRD Step 2.1 SC2/SC3）
DEFAULT_FAILURE_THRESHOLD = 5  # 连续失败 5 次触发
DEFAULT_COOLDOWN = 60  # 冷却 60s（CIRCUIT_BREAKER_TIMEOUT 可覆盖）
DEFAULT_ERROR_RATE_WINDOW = 60  # 错误率统计窗口（秒）
DEFAULT_ERROR_RATE_THRESHOLD = 0.30  # 窗口内错误率 > 30% 触发
DEFAULT_ERROR_RATE_MIN_CALLS = 5  # 窗口内至少 5 次调用才统计错误率（避免样本太少）
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
        cooldown: int = DEFAULT_COOLDOWN,
        error_rate_window: int = DEFAULT_ERROR_RATE_WINDOW,
        error_rate_threshold: float = DEFAULT_ERROR_RATE_THRESHOLD,
        error_rate_min_calls: int = DEFAULT_ERROR_RATE_MIN_CALLS,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.error_rate_window = error_rate_window
        self.error_rate_threshold = error_rate_threshold
        self.error_rate_min_calls = error_rate_min_calls
        # 内存降级模式（Redis 不可用时用）
        self._memory_store: dict[str, CircuitBreakerState] = {}
        # 调用记录：key -> deque[(timestamp, success)]，用于错误率统计
        self._memory_calls: dict[str, deque[tuple[float, bool]]] = {}
        # P1-2 (PR#138 R2): 内存模式下半开状态 RMW 原子保护——
        # asyncio.Lock 确保 probe_in_flight 的 read-modify-write 串行化
        self._state_lock = asyncio.Lock()

    async def before_call(self, key: str) -> None:
        """调用前检查熔断状态。OPEN 或 HALF_OPEN 满则抛 CircuitOpenError。"""
        state = await self._get_state(key)
        now = time.time()
        if state.opened_at is None and not state.half_open:
            return  # CLOSED
        if state.half_open:
            # 半开：P1 LOG-4——限制探测数只放行 HALF_OPEN_PROBE_LIMIT 个
            # P1-2 (PR#138 R2): asyncio.Lock 保护 read-modify-write——
            # 检查 probe_in_flight → 设置 → 写回 三步原子化
            async with self._state_lock:
                # 重新读 state——等锁期间可能已被其他协程变更
                state = await self._get_state(key)
                if state.probe_in_flight:
                    raise CircuitOpenError(
                        f"熔断器半开探测已满（key={key}），探测完成后重试"
                    )
                state.probe_in_flight = True
                await self._set_state(key, state)
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
        raise CircuitOpenError(f"熔断器开启中（key={key}），{remaining}s 后进入半开探测")

    async def record_success(self, key: str) -> None:
        """记录成功。半开状态下成功 → CLOSED。"""
        state = await self._get_state(key)
        state.failure_count = 0
        state.opened_at = None
        state.half_open = False
        state.probe_in_flight = False  # P1 LOG-4
        await self._set_state(key, state)
        self._record_call(key, True)

    async def record_failure(self, key: str) -> None:
        """记录失败。

        触发条件（任一满足即 OPEN）：
        ① 连续失败次数 >= failure_threshold
        ② 错误率窗口内错误率 > error_rate_threshold（且样本数 >= min_calls）
        半开状态下失败 → 直接重回 OPEN。
        """
        state = await self._get_state(key)
        if state.half_open:
            # 半开失败 → 重新打开
            state.half_open = False
            state.probe_in_flight = False  # P1 LOG-4
            state.opened_at = time.time()
            await self._set_state(key, state)
            logger.warning("circuit_reopened_after_probe_fail", key=key)
            return
        state.failure_count += 1
        self._record_call(key, False)
        # 判断是否触发熔断：连续失败阈值 或 错误率超阈值
        should_open = state.failure_count >= self.failure_threshold
        if not should_open:
            error_rate = self._compute_error_rate(key)
            if error_rate is not None and error_rate > self.error_rate_threshold:
                should_open = True
                logger.warning(
                    "circuit_opened_by_error_rate",
                    key=key,
                    error_rate=round(error_rate, 3),
                    threshold=self.error_rate_threshold,
                )
        if should_open:
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
        """记录调用结果，按时间窗口裁剪（修复 P1-1：原 if True 死代码）。"""
        now = time.time()
        dq = self._memory_calls.get(key)
        if dq is None:
            dq = deque(maxlen=1000)
            self._memory_calls[key] = dq
        dq.append((now, success))
        # 裁剪窗口外的记录（只保留 error_rate_window 内的）
        cutoff = now - self.error_rate_window
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    def _compute_error_rate(self, key: str) -> float | None:
        """计算错误率。样本不足返回 None（不参与熔断判断）。"""
        dq = self._memory_calls.get(key)
        if not dq:
            return None
        if len(dq) < self.error_rate_min_calls:
            return None
        failures = sum(1 for _, ok in dq if not ok)
        return failures / len(dq)
