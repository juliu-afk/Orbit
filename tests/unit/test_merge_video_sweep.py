"""merge_engine + video_tools extended tests."""
import pytest
from datetime import datetime, UTC, timedelta

class TestMergeEngineExtras:
    def test_evaluation_dimensions_valid(self):
        from orbit.scheduler.merge_engine import EVALUATION_DIMENSIONS
        for d in EVALUATION_DIMENSIONS:
            assert "key" in d
            assert "weight" in d
            assert isinstance(d["weight"], int)
            assert d["weight"] > 0

    def test_merge_result_fields(self):
        from orbit.scheduler.merge_engine import MergeResult
        r = MergeResult(merged={}, scorer="test", scorecard={}, taken_from={}, gaps_filled=[], total_scores={})
        assert r.scorer == "test"
        assert r.gaps_filled == []

class TestVideoToolsExtras:
    def test_frame_budget_auto_all_durations(self):
        from orbit.tools.video_tools import FrameBudget
        for dur, expected_fps in [(10, 1.0), (15, 1.0), (30, 1.0), (60, 0.5), (180, 0.5), (300, 0.2), (600, 0.2), (900, 0.1)]:
            b = FrameBudget.auto(dur)
            assert b.fps == expected_fps, f"duration={dur}: expected fps={expected_fps}, got {b.fps}"

    def test_watch_video_schema_valid(self):
        from orbit.tools.video_tools import WATCH_VIDEO_SCHEMA
        assert WATCH_VIDEO_SCHEMA.name == "watch_video"
        assert "url" in WATCH_VIDEO_SCHEMA.parameters
