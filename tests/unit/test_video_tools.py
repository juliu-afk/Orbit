"""V15.1 多模态 P1：video_tools 单元测试。

测试纯函数——不涉及 yt-dlp/ffmpeg 子进程调用。
"""

import pytest
from orbit.tools.video_tools import FrameBudget, _parse_time


class TestFrameBudget:
    """FrameBudget.auto()——自适应帧预算。"""

    def test_very_short_video(self):
        """≤30s → 30帧 @ 1.0fps"""
        b = FrameBudget.auto(10)
        assert b.max_frames == 30
        assert b.fps == 1.0

    def test_boundary_30s(self):
        """恰好 30s → 30帧"""
        b = FrameBudget.auto(30)
        assert b.max_frames == 30

    def test_medium_video(self):
        """30s-3m → 60帧 @ 0.5fps"""
        b = FrameBudget.auto(120)
        assert b.max_frames == 60
        assert b.fps == 0.5

    def test_boundary_180s(self):
        """恰好 3m → 60帧"""
        b = FrameBudget.auto(180)
        assert b.max_frames == 60

    def test_long_video(self):
        """3m-10m → 100帧 @ 0.2fps"""
        b = FrameBudget.auto(400)
        assert b.max_frames == 100
        assert b.fps == 0.2

    def test_boundary_600s(self):
        """恰好 10m → 100帧"""
        b = FrameBudget.auto(600)
        assert b.max_frames == 100

    def test_very_long_video(self):
        """>10m → 100帧 @ 0.1fps（封顶）"""
        b = FrameBudget.auto(3600)
        assert b.max_frames == 100
        assert b.fps == 0.1

    def test_default_width(self):
        """默认宽 512px"""
        b = FrameBudget.auto(60)
        assert b.width == 512

    def test_custom_width(self):
        """自定义宽度"""
        b = FrameBudget(50, 0.5, width=1024)
        assert b.width == 1024


class TestParseTime:
    """_parse_time()——时间字符串→秒。"""

    def test_pure_seconds(self):
        assert _parse_time("90") == 90.0

    def test_mm_ss(self):
        assert _parse_time("1:30") == 90.0

    def test_hh_mm_ss(self):
        assert _parse_time("1:00:00") == 3600.0

    def test_hh_mm_ss_with_decimal(self):
        assert _parse_time("2:30:00") == 9000.0

    def test_with_whitespace(self):
        assert _parse_time("  1:30  ") == 90.0

    def test_float_seconds(self):
        assert _parse_time("45.5") == 45.5
