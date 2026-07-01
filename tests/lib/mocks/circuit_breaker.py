"""Mock 熔断器——替代 gateway/circuit_breaker.py:CircuitBreaker。

模拟 CLOSED → OPEN → HALF_OPEN → CLOSED 状态转换。
不依赖 Redis，纯内存实现。

使用示例:
    # 正常状态
    cb = MockCircuitBreaker(state="CLOSED")
    # 熔断打开
    cb = MockCircuitBreaker(state="OPEN")
    # 半开探测
    cb = MockCircuitBreaker(state="HALF_OPEN")
"""

from __future__ import annotations

from orbit.gateway.schemas import CircuitBreakerState


class CircuitOpenError(Exception):
    """熔断器打开时抛出——兼容生产 CircuitOpenError。"""


class MockCircuitBreaker:
    """Mock 熔断器——替代 gateway/circuit_breaker.py:CircuitBreaker。

    100% 兼容 before_call()/record_success()/record_failure() 接口。
    状态转换规则与生产一致：CLOSED→OPEN→HALF_OPEN→CLOSED。
    """

    def __init__(
        self,
        state: str = "CLOSED",
        failure_count: int = 0,
        error_rate: float = 0.0,
    ) -> None:
        """初始化 Mock 熔断器。

        Args:
            state: 初始状态（CLOSED/OPEN/HALF_OPEN）
            failure_count: 当前失败计数
            error_rate: 错误率（0.0-1.0）
        """
        self.state = state.upper()
        self.failure_count = failure_count
        self.error_rate = error_rate

        # 调用追踪
        self.before_calls: list[str] = []      # 记录 before_call 的 model
        self.success_calls: list[str] = []     # 记录 record_success 的 model
        self.failure_calls: list[str] = []     # 记录 record_failure 的 model

    # ── 链式配置方法 ──────────────────────────────────────

    def set_open(self) -> "MockCircuitBreaker":
        """设置为 OPEN 状态。"""
        self.state = "OPEN"
        return self

    def set_half_open(self) -> "MockCircuitBreaker":
        """设置为 HALF_OPEN 状态。"""
        self.state = "HALF_OPEN"
        return self

    def set_closed(self) -> "MockCircuitBreaker":
        """设置为 CLOSED 状态。"""
        self.state = "CLOSED"
        return self

    def with_failures(self, count: int) -> "MockCircuitBreaker":
        """设置失败计数。"""
        self.failure_count = count
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    async def before_call(self, model: str) -> None:
        """调用前检查——兼容 CircuitBreaker.before_call()。

        Raises:
            CircuitOpenError: 当前状态为 OPEN 时
        """
        self.before_calls.append(model)

        if self.state == "OPEN":
            raise CircuitOpenError(f"Circuit breaker OPEN for model {model}")

    async def record_success(self, model: str) -> None:
        """记录成功——兼容 CircuitBreaker.record_success()。

        HALF_OPEN 状态下探测成功 → CLOSED（自动恢复）。
        """
        self.success_calls.append(model)

        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            self.error_rate = 0.0

    async def record_failure(self, model: str) -> None:
        """记录失败——兼容 CircuitBreaker.record_failure()。

        HALF_OPEN 状态下探测失败 → OPEN。
        """
        self.failure_calls.append(model)
        self.failure_count += 1

        if self.state == "HALF_OPEN":
            self.state = "OPEN"

    @property
    def current_state(self) -> str:
        """当前熔断器状态。"""
        return self.state

    def reset(self) -> None:
        """重置所有状态和追踪。"""
        self.state = "CLOSED"
        self.failure_count = 0
        self.error_rate = 0.0
        self.before_calls.clear()
        self.success_calls.clear()
        self.failure_calls.clear()
