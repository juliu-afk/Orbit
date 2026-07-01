"""测试库自身测试——mocks/ 模块。

验证所有 Mock 行为正确：正常响应/失败注入/调用追踪/reset。
"""

from __future__ import annotations

import pytest

from tests.lib.factories.llm import create_llm_request
from tests.lib.mocks import (
    MockCheckpointManager,
    MockCircuitBreaker,
    MockEventBus,
    MockKnowledgeStore,
    MockLLMClient,
    MockSandbox,
    MockToolRegistry,
)
from tests.lib.mocks.llm_client import LLMError
from tests.lib.mocks.tool_registry import DoomLoopError, RateLimitError


# ── MockLLMClient ───────────────────────────────────────

class TestMockLLMClient:
    @pytest.mark.asyncio
    async def test_normal_response(self):
        mock = MockLLMClient(fixed_response="hello")
        req = create_llm_request(prompt="test")
        resp = await mock.generate(req, task_id="t1")
        assert resp.content == "hello"
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_fail_count(self):
        mock = MockLLMClient(fail_count=2)
        req = create_llm_request()
        with pytest.raises(LLMError):
            await mock.generate(req, task_id="t1")
        with pytest.raises(LLMError):
            await mock.generate(req, task_id="t1")
        # 第 3 次成功
        resp = await mock.generate(req, task_id="t1")
        assert resp.content == "[mock] CODE_GENERATED_OK"
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_chainable_config(self):
        mock = MockLLMClient().with_failures(3).with_response("chain").with_latency(1)
        assert mock._fail_count == 3
        assert mock._fixed_response.content == "chain"
        assert mock._latency_ms == 1

    @pytest.mark.asyncio
    async def test_call_tracking(self):
        mock = MockLLMClient()
        req1 = create_llm_request(prompt="a")
        req2 = create_llm_request(prompt="b")
        await mock.generate(req1, task_id="t1")
        await mock.generate(req2, task_id="t2")
        assert len(mock.calls) == 2
        assert mock.calls[0].prompt == "a"

    def test_reset(self):
        mock = MockLLMClient(fail_count=5)
        mock.reset()
        assert mock.call_count == 0
        assert mock.calls == []
        assert mock.stream_call_count == 0

    @pytest.mark.asyncio
    async def test_stream_with_chunks(self):
        mock = MockLLMClient(stream_chunks=["def ", "foo", "(): pass"])
        events = []
        async for evt in mock.generate_stream_with_tools(create_llm_request()):
            events.append(evt)
        assert len(events) == 3
        assert events[0][1]["delta"] == "def "

    @pytest.mark.asyncio
    async def test_stream_with_tool_calls(self):
        mock = MockLLMClient(
            tool_calls=[{"name": "read_file", "args": {"path": "x.py"}}]
        )
        events = []
        async for evt in mock.generate_stream_with_tools(create_llm_request()):
            events.append(evt)
        # THINKING + TOOL_CALL
        assert len(events) >= 2


# ── MockSandbox ─────────────────────────────────────────

class TestMockSandbox:
    @pytest.mark.asyncio
    async def test_normal_execution(self):
        mock = MockSandbox(stdout="hello world")
        result = await mock.run("print('hello')")
        assert result == "hello world"
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout(self):
        from orbit.sandbox.executor import SandboxTimeoutError

        mock = MockSandbox(timeout_seconds=1)
        with pytest.raises(SandboxTimeoutError):
            await mock.run("while True: pass")

    @pytest.mark.asyncio
    async def test_oom(self):
        from orbit.sandbox.executor import SandboxError

        mock = MockSandbox(oom=True)
        with pytest.raises(SandboxError, match="OOM"):
            await mock.run("big array")

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        from orbit.sandbox.executor import SandboxExecutionError

        mock = MockSandbox(permission_denied=True)
        with pytest.raises(SandboxExecutionError, match="Permission"):
            await mock.run("hack")

    @pytest.mark.asyncio
    async def test_unsupported_language(self):
        from orbit.sandbox.executor import SandboxError

        mock = MockSandbox()
        with pytest.raises(SandboxError, match="仅支持 python"):
            await mock.run("console.log(1)", language="javascript")

    @pytest.mark.asyncio
    async def test_chainable(self):
        mock = MockSandbox().with_result(0, "ok").with_timeout(5)
        assert mock.exit_code == 0
        assert mock.timeout_seconds == 5

    def test_reset(self):
        mock = MockSandbox()
        mock.call_count = 10
        mock.reset()
        assert mock.call_count == 0


# ── MockCheckpointManager ───────────────────────────────

class TestMockCheckpointManager:
    @pytest.mark.asyncio
    async def test_save_and_load(self):
        from tests.lib.factories.checkpoint import create_checkpoint

        mock = MockCheckpointManager()
        ck = create_checkpoint(task_id="t1", state="CODING")
        await mock.save("t1", ck)
        loaded = await mock.load("t1")
        assert loaded is not None
        assert loaded.state == "CODING"
        assert mock.checkpoint_count == 1

    @pytest.mark.asyncio
    async def test_load_missing_returns_none(self):
        mock = MockCheckpointManager()
        result = await mock.load("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_version_conflict(self):
        from orbit.checkpoint.manager import CheckpointError
        from tests.lib.factories.checkpoint import create_checkpoint

        mock = MockCheckpointManager(version_conflict_on_save=True)
        ck = create_checkpoint(task_id="t1")
        await mock.save("t1", ck)
        with pytest.raises(CheckpointError, match="Version conflict"):
            await mock.save("t1", ck)

    @pytest.mark.asyncio
    async def test_degraded_logs(self):
        mock = MockCheckpointManager(redis_available=False, pg_available=False)
        from tests.lib.factories.checkpoint import create_checkpoint

        await mock.save("t1", create_checkpoint(task_id="t1"))
        assert mock.checkpoint_count == 1

    def test_save_sync(self):
        from tests.lib.factories.checkpoint import create_checkpoint

        mock = MockCheckpointManager()
        ck = create_checkpoint(task_id="t1", state="VERIFYING")
        mock.save_sync("t1", "VERIFYING", ck)
        assert mock.checkpoint_count == 1

    def test_chainable(self):
        mock = MockCheckpointManager().without_redis().without_pg()
        assert not mock.redis_available
        assert not mock.pg_available


# ── MockCircuitBreaker ──────────────────────────────────

class TestMockCircuitBreaker:
    @pytest.mark.asyncio
    async def test_closed_allows_calls(self):
        cb = MockCircuitBreaker(state="CLOSED")
        await cb.before_call("m1")
        assert len(cb.before_calls) == 1

    @pytest.mark.asyncio
    async def test_open_blocks_calls(self):
        from tests.lib.mocks.circuit_breaker import CircuitOpenError

        cb = MockCircuitBreaker(state="OPEN")
        with pytest.raises(CircuitOpenError):
            await cb.before_call("m1")

    @pytest.mark.asyncio
    async def test_half_open_probe_success(self):
        cb = MockCircuitBreaker(state="HALF_OPEN")
        await cb.before_call("probe")
        await cb.record_success("probe")
        assert cb.current_state == "CLOSED"

    @pytest.mark.asyncio
    async def test_half_open_probe_fails(self):
        cb = MockCircuitBreaker(state="HALF_OPEN")
        await cb.record_failure("probe")
        assert cb.current_state == "OPEN"

    def test_chainable(self):
        cb = MockCircuitBreaker(state="CLOSED").set_open().with_failures(3)
        assert cb.current_state == "OPEN"
        assert cb.failure_count == 3


# ── MockEventBus ────────────────────────────────────────

class TestMockEventBus:
    def test_publish_and_track(self):
        bus = MockEventBus()
        bus.publish({"type": "task:update", "task_id": "t1"})
        assert bus.event_count == 1
        assert bus.publish_count == 1

    def test_queue_full_drops(self):
        bus = MockEventBus(queue_full=True)
        bus.publish({"type": "test"})
        assert bus.dropped_count == 1
        assert bus.event_count == 0

    def test_get_events_by_type(self):
        bus = MockEventBus()
        bus.publish({"type": "task:update", "task_id": "t1"})
        bus.publish({"type": "task:update", "task_id": "t2"})
        bus.publish({"type": "dag:complete", "dag_id": "d1"})
        filtered = bus.get_events_by_type("task:update")
        assert len(filtered) == 2

    def test_reset(self):
        bus = MockEventBus()
        bus.publish({"type": "test"})
        bus.reset()
        assert bus.event_count == 0


# ── MockToolRegistry ────────────────────────────────────

class TestMockToolRegistry:
    @pytest.mark.asyncio
    async def test_dispatch_with_result(self):
        reg = MockToolRegistry(tool_results={"read_file": "file content"})
        result = await reg.dispatch("read_file", {"path": "a.py"})
        assert result == "file content"

    @pytest.mark.asyncio
    async def test_dispatch_default(self):
        reg = MockToolRegistry()
        result = await reg.dispatch("unknown_tool", {})
        assert "[mock]" in result

    @pytest.mark.asyncio
    async def test_rate_limited(self):
        reg = MockToolRegistry(rate_limited=True)
        with pytest.raises(RateLimitError):
            await reg.dispatch("read_file", {})

    @pytest.mark.asyncio
    async def test_doom_loop_detection(self):
        reg = MockToolRegistry(doom_loop_detect=True)
        await reg.dispatch("edit_file", {"path": "x.py"})
        await reg.dispatch("edit_file", {"path": "x.py"})
        with pytest.raises(DoomLoopError):
            await reg.dispatch("edit_file", {"path": "x.py"})

    def test_invoke_sync(self):
        reg = MockToolRegistry(tool_results={"grep": "matches"})
        result = reg.invoke("grep", {"pattern": "foo"}, "qa")
        assert result == "matches"

    def test_chainable(self):
        reg = MockToolRegistry().with_result("grep", "ok").with_rate_limited()
        assert reg._tool_results["grep"] == "ok"
        assert reg.rate_limited is True


# ── MockKnowledgeStore ──────────────────────────────────

class TestMockKnowledgeStore:
    def test_query_exact_hit(self):
        ks = MockKnowledgeStore(
            query_results=[{"domain": "accounting", "concept": "CurrentRatio", "value": 1.5}]
        )
        result = ks.query_exact("accounting", "CurrentRatio")
        assert result is not None
        assert result["value"] == 1.5

    def test_query_exact_miss(self):
        ks = MockKnowledgeStore()
        result = ks.query_exact("accounting", "UnknownConcept")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_hit(self):
        ks = MockKnowledgeStore(
            query_results=[{"domain": "acc", "concept": "ratio"}]
        )
        results = await ks.query("acc", "ratio")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_miss_with_low_hit_rate(self):
        ks = MockKnowledgeStore(
            query_results=[{"domain": "acc", "concept": "ratio"}],
            hit_rate=0.0,  # 永远不命中
        )
        results = await ks.query("acc", "ratio")
        assert results == []

    def test_chainable(self):
        ks = MockKnowledgeStore().with_results([{"domain": "a", "concept": "b"}]).with_hit_rate(1.0)
        assert ks.hit_rate == 1.0
        assert ks.query_exact("a", "b") is not None
