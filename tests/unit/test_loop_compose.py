import pytest
from unittest.mock import MagicMock
class TestLoopModels:
    def test_schedule(self):
        from orbit.loop.models import LoopSchedule
        s = LoopSchedule(interval_seconds=300, command="/goal test")
        assert s.interval_seconds == 300
    def test_runner(self):
        from orbit.loop.models import LoopRunner
        r = LoopRunner()
        assert r is not None
class TestLoopParser:
    def test_parse(self):
        from orbit.loop.parser import CronParser
        r = CronParser().parse("*/5 * * * *")
        assert r is not None
class TestCompose:
    def test_engine(self):
        from orbit.compose.engine import ComposeEngine
        assert ComposeEngine() is not None
