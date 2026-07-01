"""Mock 熔断器——替代 gateway/circuit_breaker.py:CircuitBreaker。

模拟 CLOSED → OPEN → HALF_OPEN → CLOSED 状态转换，纯内存实现。
"""

from __future__ import annotations


class CircuitOpenError(Exception):
    """熔断器打开时抛出——兼容生产 CircuitOpenError。"""


class MockCircuitBreaker:
    """Mock 熔断器——替代 gateway/circuit_breaker.py:CircuitBreaker。100% 兼容 before_call/record_success/record_failure。"""

    def __init__(self, state: str = "CLOSED", failure_count: int = 0, error_rate: float = 0.0) -> None:
        self.state = state.upper()
        self.failure_count = failure_count
        self.error_rate = error_rate
        self.before_calls: list[str] = []
        self.success_calls: list[str] = []
        self.failure_calls: list[str] = []

    def set_open(self) -> "MockCircuitBreaker":
        self.state = "OPEN"
        return self

    def set_half_open(self) -> "MockCircuitBreaker":
        self.state = "HALF_OPEN"
        return self

    def set_closed(self) -> "MockCircuitBreaker":
        self.state = "CLOSED"
        return self

    def with_failures(self, count: int) -> "MockCircuitBreaker":
        self.failure_count = count
        return self

    async def before_call(self, model: str) -> None:
        self.before_calls.append(model)
        if self.state == "OPEN":
            raise CircuitOpenError(f"Circuit breaker OPEN for model {model}")

    async def record_success(self, model: str) -> None:
        self.success_calls.append(model)
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failure_count = 0
            self.error_rate = 0.0

    async def record_failure(self, model: str) -> None:
        self.failure_calls.append(model)
        self.failure_count += 1
        if self.state == "HALF_OPEN":
            self.state = "OPEN"

    @property
    def current_state(self) -> str:
        return self.state

    def reset(self) -> None:
        self.state = "CLOSED"
        self.failure_count = 0
        self.error_rate = 0.0
        self.before_calls.clear()
        self.success_calls.clear()
        self.failure_calls.clear()
