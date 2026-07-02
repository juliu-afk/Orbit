"""覆盖率补测——offpeak_scheduler 深度扩展."""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.scheduler.offpeak_scheduler import (
    DEFAULT_PEAK_CONFIGS,
    DeferredQueue,
    DeferredTask,
    PeakWindow,
    PeakWindowManager,
    ProviderPeakConfig,
)


class TestPeakWindowExtended:
    def test_window_contains_exact(self):
        w = PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "12:00") is True

    def test_window_contains_edge_start(self):
        w = PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "09:00") is True

    def test_window_contains_wrong_day(self):
        w = PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Tue", "12:00") is False

    def test_window_contains_before_start(self):
        w = PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "08:00") is False

    def test_provider_peak_config(self):
        cfg = ProviderPeakConfig(
            provider="anthropic", timezone="US/Eastern",
            peak_windows=[PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")],
            offpeak_windows=[PeakWindow(days=["Sat","Sun"], hours_start="00:00", hours_end="23:59")],
            peak_price_multiplier=1.5, offpeak_price_multiplier=0.5,
        )
        assert cfg.provider == "anthropic"


class TestPeakWindowManagerExtended:
    def test_is_peak_unknown_provider(self):
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._configs = {}
        mgr._holidays = set()
        assert mgr.is_peak("unknown") is False

    def test_default_configs_exist(self):
        assert "deepseek" in DEFAULT_PEAK_CONFIGS
        assert "anthropic" in DEFAULT_PEAK_CONFIGS

    def test_is_holiday_offpeak(self):
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._configs = {
            "deepseek": ProviderPeakConfig(
                provider="deepseek", timezone="Asia/Shanghai",
                peak_windows=[PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="00:00", hours_end="23:59")],
                offpeak_windows=[],
                peak_price_multiplier=1.0, offpeak_price_multiplier=0.7,
            ),
        }
        today_str = date.today().isoformat()
        mgr._holidays = {today_str}
        assert mgr.is_peak("deepseek") is False


class TestDeferredQueueExtended:
    @pytest.fixture
    def queue(self, tmp_path):
        db_path = str(tmp_path / "test_q.db")
        return DeferredQueue(db_path)

    @pytest.mark.asyncio
    async def test_push_and_pop(self, queue):
        task = DeferredTask(
            id="task-1", goal_description="test",
            priority="NORMAL", provider="deepseek",
            estimated_tokens=50000, estimated_duration_seconds=300,
            target_window_start="2026-01-01T00:00:00", target_window_end="2026-01-01T08:00:00",
            status="pending",
        )
        pos = await queue.push(task)
        assert pos >= 1

        popped = await queue.pop_for_window(
            "2026-01-01T00:00:00", "2026-01-01T08:00:00", limit=10,
        )
        assert len(popped) >= 1

    @pytest.mark.asyncio
    async def test_pop_empty_window(self, queue):
        popped = await queue.pop_for_window(
            "2999-01-01T00:00:00", "2999-01-01T08:00:00", limit=10,
        )
        assert popped == []
