"""Gateway/通信模块覆盖率补充测试."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.gateway.schemas import LLMRequest
from orbit.communication.message_bus import AgentMessageBus


class TestLLMRequest:
    """LLMRequest 模型测试."""

    def test_request_defaults(self) -> None:
        """默认字段正确."""
        req = LLMRequest(prompt="test")
        assert req.prompt == "test"
        assert len(req.system_prompt) > 0  # 有默认系统提示
        assert isinstance(req.temperature, float)

    def test_request_full(self) -> None:
        """完整字段设置."""
        req = LLMRequest(
            prompt="hello",
            system_prompt="be helpful",
            temperature=0.7,
            max_tokens=1000,
        )
        assert req.prompt == "hello"
        assert req.system_prompt == "be helpful"
        assert req.temperature == 0.7
        assert req.max_tokens == 1000


class TestAgentMessageBus:
    """AgentMessageBus 导入测试."""

    def test_init_empty(self) -> None:
        """空初始化."""
        bus = AgentMessageBus()
        assert bus is not None

    def test_subscribe_unsubscribe_no_error(self) -> None:
        """订阅/取消不崩溃."""
        bus = AgentMessageBus()
        bus.register("test_handler", lambda m: None)
        bus.unregister("test_handler")

    def test_no_subscribers_no_error(self) -> None:
        """空总线操作不崩溃."""
        bus = AgentMessageBus()
        assert bus.is_registered("nonexistent") is False


class TestCircuitBreaker:
    """熔断器状态测试."""

    def test_circuit_breaker_state_defaults(self) -> None:
        """默认状态."""
        from orbit.gateway.schemas import CircuitBreakerState

        state = CircuitBreakerState()
        assert state.failure_count == 0
        assert state.opened_at is None
        assert state.half_open is False

    def test_circuit_breaker_failure_accumulation(self) -> None:
        """失败累加."""
        from orbit.gateway.schemas import CircuitBreakerState

        state = CircuitBreakerState()
        state.failure_count += 1
        state.failure_count += 1
        assert state.failure_count == 2


class TestGatewayConstants:
    """网关常量测试."""

    def test_model_constants_defined(self) -> None:
        """模型常量已定义."""
        from orbit.gateway.client import MODEL_FLASH, MODEL_PRO, MODEL_GLM5

        assert MODEL_FLASH is not None
        assert MODEL_PRO is not None
        assert MODEL_GLM5 is not None

    def test_circuit_breaker_constants(self) -> None:
        """熔断器阈值常量."""
        from orbit.gateway.circuit_breaker import (
            DEFAULT_COOLDOWN,
            DEFAULT_FAILURE_THRESHOLD,
            HALF_OPEN_PROBE_LIMIT,
        )

        assert DEFAULT_FAILURE_THRESHOLD > 0
        assert DEFAULT_COOLDOWN > 0
        assert HALF_OPEN_PROBE_LIMIT > 0


# -- LLMClient.generate() 深度覆盖 --


class TestLLMClientGenerate:
    """覆盖 generate() 所有分支: 默认/路由策略/任务类型/Agent路由/熔断/降级。"""

    @pytest.fixture
    def mock_cb(self):
        from orbit.gateway.circuit_breaker import CircuitBreaker
        return CircuitBreaker()

    @pytest.fixture
    def client(self, mock_cb):
        from orbit.gateway.client import LLMClient
        return LLMClient(circuit_breaker=mock_cb)

    @pytest.mark.asyncio
    async def test_default_path(self, client, monkeypatch):
        """无路由策略/无 resolver → 使用 default_model → 成功。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        async def fake_do(self, model, req):
            return LLMResponse(content="ok", model=model, usage=LLMUsage())

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1")
        assert resp.content == "ok"

    @pytest.mark.asyncio
    async def test_routing_strategy_path(self, client, monkeypatch):
        """routing_strategy 非 AGENT_DEFAULT → select_model → 使用策略模型。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage
        from orbit.gateway.routing import RoutingStrategy

        async def fake_do(self, model, req):
            return LLMResponse(content="cheap", model=model, usage=LLMUsage())

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1", routing_strategy=RoutingStrategy.CHEAPEST)
        assert resp.content == "cheap"

    @pytest.mark.asyncio
    async def test_task_type_routing_path(self, client, monkeypatch):
        """task_type 参数 → task_router.select → 使用任务模型。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        async def fake_do(self, model, req):
            return LLMResponse(content="reasoning", model=model, usage=LLMUsage())

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1", task_type="reasoning")
        assert resp.content == "reasoning"

    @pytest.mark.asyncio
    async def test_task_type_routing_failure_fallback(self, client, monkeypatch):
        """task_router 异常 → 使用 default_model 继续。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        client.task_router.select = MagicMock(side_effect=RuntimeError("boom"))
        async def fake_do(self, model, req):
            return LLMResponse(content="default_ok", model=model, usage=LLMUsage())

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1", task_type="reasoning")
        assert resp.content == "default_ok"

    @pytest.mark.asyncio
    async def test_primary_circuit_open_fallback(self, client, monkeypatch):
        """主力模型熔断 → 降级到 fallback_model。"""
        from orbit.gateway.circuit_breaker import CircuitOpenError
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        call_log = []
        async def fake_do(self, model, req):
            call_log.append(model)
            if "glm-4.7" in model:
                return LLMResponse(content="fallback_ok", model=model, usage=LLMUsage())
            raise CircuitOpenError(model)

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1")
        assert resp.content == "fallback_ok"
        assert "openai/glm-4.7-flash" in call_log

    @pytest.mark.asyncio
    async def test_primary_api_error_fallback(self, client, monkeypatch):
        """主力 API 错误（TimeoutError）→ 降级 fallback。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        call_log = []
        async def fake_do(self, model, req):
            call_log.append(model)
            if "glm-4.7" in model:
                return LLMResponse(content="fallback_ok", model=model, usage=LLMUsage())
            raise TimeoutError("timeout")

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1")
        assert resp.content == "fallback_ok"

    @pytest.mark.asyncio
    async def test_primary_unexpected_error_raises(self, client, monkeypatch):
        """非 API 错误（代码 bug）→ 直接 raise，不降级。"""
        async def fake_do(self, model, req):
            raise TypeError("code bug")

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        with pytest.raises(TypeError, match="code bug"):
            await client.generate(LLMRequest(prompt="x"), "t1")

    @pytest.mark.asyncio
    async def test_fallback_circuit_open_raises(self, client, monkeypatch):
        """主力和 fallback 都熔断 → raise CircuitOpenError。"""
        from orbit.gateway.circuit_breaker import CircuitOpenError

        async def fake_do(self, model, req):
            raise CircuitOpenError(model)

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        with pytest.raises(CircuitOpenError):
            await client.generate(LLMRequest(prompt="x"), "t1")

    @pytest.mark.asyncio
    async def test_fallback_failed_raises(self, client, monkeypatch):
        """主力熔断 + fallback 网络异常 → raise。"""
        from orbit.gateway.circuit_breaker import CircuitOpenError
        from orbit.gateway.schemas import LLMResponse, LLMUsage

        call_log = []
        async def fake_do(self, model, req):
            call_log.append(model)
            if "glm-4.7" in model:
                raise ConnectionError("network down")
            raise CircuitOpenError(model)

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        with pytest.raises(ConnectionError):
            await client.generate(LLMRequest(prompt="x"), "t1")

    @pytest.mark.asyncio
    async def test_agent_resolver_path(self, client, monkeypatch):
        """有 resolver + agent_name → 调用 resolver.resolve 选择模型。"""
        from orbit.gateway.schemas import LLMResponse, LLMUsage
        from unittest.mock import AsyncMock

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=MagicMock(model="resolved-model", source="agent_config"))
        client.resolver = mock_resolver

        async def fake_do(self, model, req):
            return LLMResponse(content="resolved_ok", model=model, usage=LLMUsage())

        monkeypatch.setattr("orbit.gateway.client.LLMClient._do_completion", fake_do)
        resp = await client.generate(LLMRequest(prompt="x"), "t1", agent_name="developer")
        assert resp.content == "resolved_ok"
