"""loop/models + router/agent extended tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.loop.models import LoopRunner, LoopSchedule
from orbit.router.agent import RouterAgent


class TestLoopModels:
    def test_loop_schedule_create(self):
        s = LoopSchedule(interval_seconds=300, command="/goal test")
        assert s.interval_seconds == 300
        assert s.command == "/goal test"


class TestRouterAgent:
    def test_init(self):
        ra = RouterAgent()
        assert ra is not None

    def test_init_with_bandit(self):
        ra = RouterAgent(bandit=MagicMock())
        assert ra._bandit is not None
