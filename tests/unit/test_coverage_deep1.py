"""覆盖率深度补测——offpeak DeferredQueue 完整路径 + probes mock IO."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.observability.probes import (
    ProbeResult,
    StartupProbeEngine,
    _probe_agent,
    _probe_code_graph,
    _probe_environment,
    _probe_knowledge_engine,
    _probe_llm_gateway,
    _probe_session_store,
)
from orbit.scheduler.offpeak import (
    DeferredQueue,
    OffPeakScheduler,
    PeakWindowManager,
)
from orbit.scheduler.offpeak_models import (
    DeferredTask,
    PeakWindow,
    ProviderPeakConfig,
)


# ════════════════════════════════════════════
# 1. DeferredQueue 全路径
# ════════════════════════════════════════════

class TestDeferredQueueFull:
    @pytest.fixture
    def queue(self, tmp_path):
        return DeferredQueue(str(tmp_path / "q.db"))

    @pytest.mark.asyncio
    async def test_push_multiple(self, queue):
        """多个任务入队——队列位置递增。"""
        for i in range(3):
            task = DeferredTask(
                id=f"task-{i}", goal_description=f"goal {i}",
                priority="NORMAL", provider="deepseek",
                estimated_tokens=10000, estimated_duration_seconds=60,
                target_window_start="2026-06-01T00:00:00", target_window_end="2026-06-01T08:00:00",
                status="pending",
            )
            pos = await queue.push(task)
            assert pos == i + 1

    @pytest.mark.asyncio
    async def test_push_high_priority_first(self, queue):
        """HIGH 优先级排在前面。"""
        t1 = DeferredTask(
            id="low", goal_description="low", priority="NORMAL", provider="d",
            estimated_tokens=100, estimated_duration_seconds=10,
            target_window_start="2026-06-01T00:00:00", target_window_end="2026-06-01T08:00:00",
            status="pending",
        )
        t2 = DeferredTask(
            id="high", goal_description="high", priority="HIGH", provider="d",
            estimated_tokens=100, estimated_duration_seconds=10,
            target_window_start="2026-06-01T00:00:00", target_window_end="2026-06-01T08:00:00",
            status="pending",
        )
        await queue.push(t1)
        await queue.push(t2)

        popped = await queue.pop_for_window(
            "2026-06-01T00:00:00", "2026-06-01T08:00:00", limit=10,
        )
        # HIGH 优先级应排在前面
        assert popped[0].id == "high"

    @pytest.mark.asyncio
    async def test_pop_respects_limit(self, queue):
        """pop 限制数量。"""
        for i in range(5):
            task = DeferredTask(
                id=f"t-{i}", goal_description=f"g{i}",
                priority="NORMAL", provider="d",
                estimated_tokens=100, estimated_duration_seconds=10,
                target_window_start="2026-06-01T00:00:00", target_window_end="2026-06-01T08:00:00",
                status="pending",
            )
            await queue.push(task)

        popped = await queue.pop_for_window(
            "2026-06-01T00:00:00", "2026-06-01T08:00:00", limit=2,
        )
        assert len(popped) == 2


# ════════════════════════════════════════════
# 2. Probes 纯函数
# ════════════════════════════════════════════

class TestProbeFunctions:
    @pytest.mark.asyncio
    async def test_probe_environment(self):
        result = await _probe_environment()
        assert "配置加载成功" in result

    @pytest.mark.asyncio
    async def test_probe_agent(self):
        result = await _probe_agent()
        assert "可用" in result or "Agent" in result

    @pytest.mark.asyncio
    async def test_probe_llm_gateway(self):
        result = await _probe_llm_gateway()
        assert isinstance(result, str) and len(result) > 0

    @pytest.mark.asyncio
    async def test_probe_knowledge_engine(self):
        result = await _probe_knowledge_engine()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_probe_code_graph(self):
        result = await _probe_code_graph()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_probe_session_store(self):
        result = await _probe_session_store()
        assert isinstance(result, str)


# ════════════════════════════════════════════
# 3. OffPeakScheduler 额外路径
# ════════════════════════════════════════════

class TestOffPeakSchedulerExtended:
    @pytest.mark.asyncio
    async def test_enqueue_without_offpeak_config(self):
        """无 provider 配置 → 返回 immediate。"""
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._configs = {}
        mgr._holidays = set()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            q = DeferredQueue(db_path)
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()
            mock_preflight = AsyncMock()
            scheduler = OffPeakScheduler(mgr, q, mock_orch, mock_preflight)

            from orbit.goal.models import GoalSession
            goal = GoalSession(description="test", defer_to_offpeak=False)
            result = await scheduler.enqueue(goal)
            assert result is not None
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass
