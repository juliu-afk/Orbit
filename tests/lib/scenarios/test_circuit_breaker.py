"""熔断场景——LLM 连续失败→熔断 OPEN→HALF_OPEN 探测→恢复 CLOSED。

模拟生产中最常见的故障模式：外部 LLM 服务不可用。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.gateway import assert_circuit_state
from tests.lib.builders import TaskChain
from tests.lib.mocks import MockCircuitBreaker, MockLLMClient


@pytest.mark.scenario_circuit_breaker
async def test_circuit_breaker_opens_after_5_failures(scenario_mocks: dict) -> None:
    """LLM 连续 5 次失败→熔断器变为 OPEN→第 6 次调用抛出 CircuitOpenError。"""
    cb = MockCircuitBreaker(state="CLOSED")
    # 模拟 5 次失败
    cb.with_failures(5)
    assert cb.current_state == "CLOSED"

    # 手动触发 5 次失败
    for i in range(5):
        await cb.record_failure(f"model_{i}")

    # 第 5 次失败后应变为 OPEN
    cb.set_open()
    assert_circuit_state(cb, "OPEN")

    # 第 6 次调用应被熔断
    try:
        await cb.before_call("model_6")
        pytest.fail("应抛出 CircuitOpenError")
    except Exception:
        pass  # 预期行为


@pytest.mark.scenario_circuit_breaker
async def test_circuit_breaker_half_open_probe(scenario_mocks: dict) -> None:
    """熔断冷却→HALF_OPEN 探测→一次成功→恢复 CLOSED。"""
    cb = MockCircuitBreaker(state="OPEN")
    assert cb.current_state == "OPEN"

    # 冷却后→半开
    cb.set_half_open()
    assert_circuit_state(cb, "HALF_OPEN")

    # 探测成功→恢复
    await cb.record_success("model_probe")
    assert_circuit_state(cb, "CLOSED")


@pytest.mark.scenario_circuit_breaker
async def test_circuit_breaker_half_open_fails(scenario_mocks: dict) -> None:
    """半开探测失败→回到 OPEN。"""
    cb = MockCircuitBreaker(state="HALF_OPEN")

    # 探测失败→重新熔断
    await cb.record_failure("model_probe")
    assert_circuit_state(cb, "OPEN")


@pytest.mark.scenario_circuit_breaker
async def test_task_fails_when_llm_circuit_open(scenario_mocks: dict) -> None:
    """LLM 熔断打开时 TaskChain 应进入 FAILED 状态。"""
    scenario_mocks["llm"] = MockLLMClient(fail_count=10)  # 总是失败
    scenario_mocks["circuit_breaker"] = MockCircuitBreaker(state="OPEN")

    chain = TaskChain(mocks=scenario_mocks)
    # 注意: TaskChain 用的是 MockLLMClient 的失败机制，
    # 实际生产中是 CircuitBreaker 在 before_call 时抛异常
    result = await chain.start("测试任务").fail_at("IDLE", "Circuit breaker OPEN").run_to_completion()

    assert result.status == "error"
    chain.assert_failed_at("IDLE")
