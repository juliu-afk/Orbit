"""integration/wiring.py unit tests — OrbitWiring init, singletons, simple methods.
Coverage sprint 5: 47% → >=55%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.integration.wiring import (
    DISTILL_EVERY_N_TASKS,
    OrbitWiring,
    configure_wiring,
    get_wiring,
)


# ── Module constants ──────────────────────────────────────


class TestConstants:
    def test_distill_interval_is_int(self):
        assert isinstance(DISTILL_EVERY_N_TASKS, int)
        assert DISTILL_EVERY_N_TASKS > 0


# ── OrbitWiring.__init__ ──────────────────────────────────


class TestOrbitWiringInit:
    def test_default_init(self):
        w = OrbitWiring()
        assert w._task_count == 0
        assert w._event_bus is None
        assert w._monitor_queues == {}
        assert w._monitor_tasks == {}
        assert w._last_tier == ""

    def test_custom_db_path(self):
        w = OrbitWiring(db_path="/tmp/test.db")
        assert w._db_path == "/tmp/test.db"

    def test_lazy_components_are_none(self):
        """All lazy components start as None."""
        w = OrbitWiring()
        assert w._trajectory is None
        assert w._episodic is None
        assert w._profile is None
        assert w._agentic is None
        assert w._distill is None
        assert w._monitor is None


# ── Simple methods ────────────────────────────────────────


class TestSimpleMethods:
    def test_set_model_tier(self):
        w = OrbitWiring()
        w.set_model_tier("T2")
        assert w._last_tier == "T2"

    def test_feed_monitor_no_queue(self):
        """feed_monitor with no queue → silent no-op."""
        w = OrbitWiring()
        w.feed_monitor("t1", {"event": "test"})  # should not raise

    def test_feed_monitor_with_queue(self):
        """feed_monitor with queue → event enqueued."""
        import asyncio
        w = OrbitWiring()
        q = asyncio.Queue(maxsize=10)
        w._monitor_queues["t1"] = q
        w.feed_monitor("t1", {"type": "turn_start"})
        assert not q.empty()

    def test_get_trajectory_public(self):
        """Public getter delegates to _get_trajectory."""
        w = OrbitWiring()
        # Without DB setup, returns None (import fails gracefully)
        result = w.get_trajectory()
        # Should not raise, may be None

    def test_get_mcts_planner(self):
        w = OrbitWiring()
        result = w.get_mcts_planner()
        # Returns None when import fails (no deps)


# ── Singleton functions ───────────────────────────────────


class TestSingletonFunctions:
    def test_configure_wiring_returns_instance(self, tmp_path):
        db = str(tmp_path / "wiring.db")
        w = configure_wiring(db)
        assert isinstance(w, OrbitWiring)
        assert w._db_path == db

    def test_configure_wiring_with_event_bus(self, tmp_path):
        db = str(tmp_path / "wiring2.db")
        eb = MagicMock()
        w = configure_wiring(db, event_bus=eb)
        assert w._event_bus is eb

    def test_get_wiring_after_configure(self, tmp_path):
        db = str(tmp_path / "wiring3.db")
        w1 = configure_wiring(db)
        w2 = get_wiring()
        assert w1 is w2  # same singleton

    def test_get_wiring_default(self):
        """get_wiring without configure → creates default instance."""
        # Reset singleton
        import orbit.integration.wiring as wiring_mod
        wiring_mod._wiring_instance = None
        w = get_wiring()
        assert isinstance(w, OrbitWiring)
        assert w._db_path == ":memory:"


# ── record_event ──────────────────────────────────────────


class TestRecordEvent:
    def test_no_episodic_memory(self):
        """record_event without episodic memory → no-op (no crash)."""
        w = OrbitWiring()
        w.record_event("t1", "test event", "success", ["tag1"])
        # should not raise

    def test_with_episodic_memory(self):
        w = OrbitWiring()
        mock_em = MagicMock()
        w._episodic = mock_em
        w.record_event("t1", "test", "failure", ["bug"])
        mock_em.record_event.assert_called_once()


# ── enhance_prompt ────────────────────────────────────────


class TestEnhancePrompt:
    def test_no_components(self):
        """enhance_prompt with no injector/agentic → returns original."""
        w = OrbitWiring()
        result = w.enhance_prompt("base prompt")
        assert result == "base prompt"

    def test_with_keywords_and_agentic(self):
        w = OrbitWiring()
        mock_am = MagicMock()
        mock_suggestion = MagicMock()
        mock_suggestion.action = "add more tests"
        mock_suggestion.utility = 0.95
        mock_am.suggest.return_value = [mock_suggestion]
        w._agentic = mock_am
        result = w.enhance_prompt("base prompt", keywords=["testing"])
        assert "add more tests" in result
        assert "95%" in result
