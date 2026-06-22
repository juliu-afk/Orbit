"""Step 2.1 LLMClient + 熔断器测试。

覆盖 PRD 验收标准：
- SC1: 正常调用返回有效内容
- SC2: 连续 5 次失败触发熔断
- SC3: 冷却后半开探测恢复
- SC4: 成本追踪
- SC5: 主备降级
"""
from __future__ import annotations

import pytest

from orbit.gateway.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from orbit.gateway.client import LLMClient
from orbit.gateway.schemas import LLMRequest, LLMUsage


@pytest.fixture
def cb():
    return CircuitBreaker(cooldown=1)  # 测试用短冷却


@pytest.fixture
def client(cb):
    return LLMClient(circuit_breaker=cb)


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold(cb):
    """SC2: 连续 5 次失败触发熔断。"""
    key = "deepseek/deepseek-chat"
    for _ in range(5):
        await cb.record_failure(key)
    # 第 6 次调用前应抛熔断异常
    with pytest.raises(CircuitOpenError):
        await cb.before_call(key)


@pytest.mark.asyncio
async def test_circuit_half_open_recovery(cb):
    """SC3: 冷却后进入半开，探测成功 → CLOSED。"""
    key = "test/model"
    for _ in range(5):
        await cb.record_failure(key)
    # 等冷却（测试用 cooldown=1）
    import time

    time.sleep(1.1)
    # 进入半开
    await cb.before_call(key)
    state = await cb.get_state(key)
    assert state.half_open is True
    # 探测成功 → CLOSED
    await cb.record_success(key)
    state = await cb.get_state(key)
    assert state.opened_at is None
    assert state.half_open is False
    assert state.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_reopen_on_half_open_fail(cb):
    """半开探测失败 → 重新 OPEN。"""
    key = "test/model"
    for _ in range(5):
        await cb.record_failure(key)
    import time

    time.sleep(1.1)
    await cb.before_call(key)
    await cb.record_failure(key)
    state = await cb.get_state(key)
    assert state.half_open is False
    assert state.opened_at is not None


@pytest.mark.asyncio
async def test_normal_call_success(client, monkeypatch):
    """SC1: 正常调用返回有效内容。"""

    async def fake_do(self, model, req):
        from orbit.gateway.schemas import LLMResponse

        return LLMResponse(
            content="def add(a, b): return a + b",
            model=model,
            usage=LLMUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=0.00002
            ),
        )

    monkeypatch.setattr(LLMClient, "_do_completion", fake_do)
    resp = await client.generate(LLMRequest(prompt="sum function"), "task-1")
    assert "add" in resp.content
    assert resp.usage.total_tokens == 15
    assert resp.usage.cost_usd > 0


@pytest.mark.asyncio
async def test_cost_tracking(client, monkeypatch):
    """SC4: 成本追踪 + get_usage_stats 累计。"""

    async def fake_do(self, model, req):
        from orbit.gateway.schemas import LLMResponse

        return LLMResponse(
            content="ok",
            model=model,
            usage=LLMUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                cost_usd=0.0002,
            ),
        )

    monkeypatch.setattr(LLMClient, "_do_completion", fake_do)
    await client.generate(LLMRequest(prompt="x"), "task-cost")
    await client.generate(LLMRequest(prompt="y"), "task-cost")
    stats = client.get_usage_stats("task-cost")
    assert stats.total_tokens == 300
    assert stats.cost_usd == pytest.approx(0.0004)


@pytest.mark.asyncio
async def test_fallback_on_primary_failure(client, monkeypatch):
    """SC5: 主力失败 → 自动切备选。"""
    call_log = []

    async def fake_do(self, model, req):
        call_log.append(model)
        if model == client.default_model:
            raise Exception("主力 API 错误")
        from orbit.gateway.schemas import LLMResponse

        return LLMResponse(
            content="fallback ok",
            model=model,
            usage=LLMUsage(),
        )

    monkeypatch.setattr(LLMClient, "_do_completion", fake_do)
    resp = await client.generate(LLMRequest(prompt="test"), "task-fallback")
    assert resp.content == "fallback ok"
    assert client.fallback_model in call_log


@pytest.mark.asyncio
async def test_all_circuits_open_raises(client, monkeypatch):
    """主备都熔断时抛 CircuitOpenError。"""
    # 手动把两个模型都熔断
    for _ in range(5):
        await client.cb.record_failure(client.default_model)
        await client.cb.record_failure(client.fallback_model)
    with pytest.raises(CircuitOpenError):
        await client.generate(LLMRequest(prompt="x"), "task-dead")


@pytest.mark.asyncio
async def test_usage_stats_empty(client):
    """未调用过的任务返回零统计。"""
    stats = client.get_usage_stats("nonexistent")
    assert stats.total_tokens == 0
    assert stats.cost_usd == 0.0