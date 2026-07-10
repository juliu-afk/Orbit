"""loop/scheduler.py extended tests — DB_PATH, constants, init.
Coverage sprint 4-2: 72% → >=80%.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from orbit.loop.scheduler import DB_PATH, LoopScheduler


class TestConstants:
    def test_max_loops(self):
        assert LoopScheduler.MAX_LOOPS == 5

    def test_db_path_exists(self):
        assert "data" in str(DB_PATH)
        assert str(DB_PATH).endswith("loop_schedules.db")


class TestLoopSchedulerInit:
    def test_default_init(self):
        s = LoopScheduler()
        assert s._parser is not None
        assert s._loops == {}
        assert s._schedules == {}
        assert s._tasks == {}

    def test_with_executor(self):
        mock_exec = MagicMock()
        s = LoopScheduler(command_executor=mock_exec)
        assert s._executor is mock_exec
