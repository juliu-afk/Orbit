"""video_tools.py extended tests — FrameBudget, constants, schema validation.
Coverage sprint 3-1: 28% → >=40%.
"""
from __future__ import annotations

import pytest

from orbit.tools.video_tools import FrameBudget, WATCH_VIDEO_SCHEMA


# ── FrameBudget ───────────────────────────────────────────


class TestFrameBudget:
    """Test FrameBudget.auto() — adaptive frame budget by duration."""

    def test_short_video(self):
        """≤30s → 30 frames @ 1.0fps."""
        b = FrameBudget.auto(15)
        assert b.max_frames == 30
        assert b.fps == 1.0

    def test_medium_video(self):
        """30s-3m → 60 frames @ 0.5fps."""
        b = FrameBudget.auto(120)
        assert b.max_frames == 60
        assert b.fps == 0.5

    def test_long_video(self):
        """3m-10m → 100 frames @ 0.2fps."""
        b = FrameBudget.auto(400)
        assert b.max_frames == 100
        assert b.fps == 0.2

    def test_very_long_video(self):
        """>10m → 100 frames @ 0.1fps (capped)."""
        b = FrameBudget.auto(1000)
        assert b.max_frames == 100
        assert b.fps == 0.1

    def test_boundary_30s(self):
        """Exactly 30s → short tier."""
        b = FrameBudget.auto(30)
        assert b.max_frames == 30

    def test_boundary_180s(self):
        """Exactly 180s → medium tier."""
        b = FrameBudget.auto(180)
        assert b.max_frames == 60

    def test_boundary_600s(self):
        """Exactly 600s → long tier."""
        b = FrameBudget.auto(600)
        assert b.max_frames == 100

    def test_default_width(self):
        b = FrameBudget(30, 1.0)
        assert b.width == 512

    def test_custom_width(self):
        b = FrameBudget(10, 2.0, width=256)
        assert b.width == 256


# ── WATCH_VIDEO_SCHEMA ────────────────────────────────────


class TestWatchVideoSchema:
    """Test WATCH_VIDEO_SCHEMA constant."""

    def test_schema_name(self):
        assert WATCH_VIDEO_SCHEMA.name == "watch_video"

    def test_schema_version(self):
        assert WATCH_VIDEO_SCHEMA.version == "1.0.0"

    def test_schema_parameters(self):
        params = WATCH_VIDEO_SCHEMA.parameters
        assert "url" in params
        assert params["url"]["type"] == "string"

    def test_schema_timeout(self):
        assert WATCH_VIDEO_SCHEMA.timeout_seconds > 0

    def test_schema_is_async(self):
        assert WATCH_VIDEO_SCHEMA.is_async is True
