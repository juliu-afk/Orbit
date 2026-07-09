"""V15.1 多模态 P1：video_capture 单元测试。

测试帧去重算法 + ScreenshotCapture 状态管理。
"""

import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from orbit.observability.video_capture import (
    ScreenshotCapture,
    ScreenshotRecord,
    DEDUP_MAD_THRESHOLD,
)


def _make_test_image(color: tuple[int, int, int] = (255, 0, 0), size=(100, 100)):
    """Helper: create a PIL Image with given color."""
    return Image.new("RGB", size, color=color)


class TestScreenshotCapture:
    """ScreenshotCapture——审计截图捕获。"""

    def test_first_frame_always_saved(self):
        """第一帧始终保存"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            img = _make_test_image((255, 0, 0))
            record = asyncio_run(cap.capture(img, "task_1", "qa", "test"))
            assert record is not None
            assert record.filepath.endswith(".jpg")
            assert record.agent_name == "qa"
            assert record.task_id == "task_1"
            assert record.decision_type == "test"
            assert Path(record.filepath).exists()

    def test_duplicate_frame_deduped(self):
        """相同帧被去重（MAD < 阈值）"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            img1 = _make_test_image((255, 0, 0))
            img2 = _make_test_image((255, 0, 0))  # 完全相同

            r1 = asyncio_run(cap.capture(img1, "t1", "qa", "test"))
            r2 = asyncio_run(cap.capture(img2, "t1", "qa", "test"))
            assert r1 is not None
            assert r2 is None  # 被去重

    def test_different_frame_saved(self):
        """不同帧被保存"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            img1 = _make_test_image((255, 0, 0))
            img2 = _make_test_image((0, 255, 0))  # 完全不同

            r1 = asyncio_run(cap.capture(img1, "t1", "qa", "test"))
            r2 = asyncio_run(cap.capture(img2, "t1", "qa", "test"))
            assert r1 is not None
            assert r2 is not None  # 不同帧，都保存

    def test_get_stats(self):
        """统计正确"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            asyncio_run(cap.capture(_make_test_image((255, 0, 0)), "t1", "qa", "t"))
            asyncio_run(cap.capture(_make_test_image((255, 0, 0)), "t1", "qa", "t"))  # dup
            asyncio_run(cap.capture(_make_test_image((0, 255, 0)), "t1", "qa", "t"))  # diff

            stats = cap.get_stats()
            assert stats["total_captured"] == 2
            assert stats["total_deduped"] == 1
            assert stats["dedup_ratio"] == 1 / 3  # 1 deduped / 3 total attempts

    def test_get_session_records_filter_by_task(self):
        """按 task_id 过滤"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            asyncio_run(cap.capture(_make_test_image((255, 0, 0)), "task_a", "qa", "t"))
            asyncio_run(cap.capture(_make_test_image((0, 255, 0)), "task_b", "qa", "t"))

            a_records = cap.get_session_records("task_a")
            assert len(a_records) == 1
            assert a_records[0].task_id == "task_a"

    def test_screenshot_dir_created(self):
        """截图目录自动创建"""
        with tempfile.TemporaryDirectory() as tmp:
            cap = ScreenshotCapture(data_dir=tmp)
            assert os.path.isdir(cap.screenshot_dir)


class TestDedupThreshold:
    """帧去重阈值行为。"""

    def test_mad_zero_for_identical(self):
        """完全相同的两帧 MAD ≈ 0"""
        img1 = _make_test_image((128, 128, 128))
        img2 = _make_test_image((128, 128, 128))

        thumb1 = img1.resize((16, 16)).convert("L")
        thumb2 = img2.resize((16, 16)).convert("L")
        pixels1 = list(thumb1.get_flattened_data())
        pixels2 = list(thumb2.get_flattened_data())

        mad = sum(abs(a - b) for a, b in zip(pixels1, pixels2)) / 256.0
        assert mad == 0.0
        assert mad < DEDUP_MAD_THRESHOLD

    def test_mad_high_for_different(self):
        """完全不同颜色的两帧 MAD >> 阈值"""
        img1 = _make_test_image((0, 0, 0))      # 纯黑
        img2 = _make_test_image((255, 255, 255))  # 纯白

        thumb1 = img1.resize((16, 16)).convert("L")
        thumb2 = img2.resize((16, 16)).convert("L")
        pixels1 = list(thumb1.get_flattened_data())
        pixels2 = list(thumb2.get_flattened_data())

        mad = sum(abs(a - b) for a, b in zip(pixels1, pixels2)) / 256.0
        assert mad > DEDUP_MAD_THRESHOLD * 10  # 黑白差异 >> 2.0


# ── async helper ──


def asyncio_run(coro):
    """Synchronous wrapper for async capture calls."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        return asyncio.run(coro)
    # Already in running event loop
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()
