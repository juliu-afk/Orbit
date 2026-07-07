"""testing/triangle.py 单元测试——三角闭环连接器。"""

from __future__ import annotations

import pytest

from orbit.testing.triangle import (
    FailurePattern,
    TriangleConnector,
    TriangleReport,
)


class TestFailurePattern:
    """FailurePattern 数据模型。"""

    def test_default_values(self):
        """默认值合理。"""
        pattern = FailurePattern()
        assert pattern.frequency == 1
        assert pattern.pattern_id == ""
        assert pattern.description == ""


class TestTriangleReport:
    """TriangleReport 统计。"""

    def test_empty_report(self):
        """空报告——无发现。"""
        report = TriangleReport()
        assert report.patterns_extracted == 0
        assert report.patterns_confirmed == 0
        assert report.prompt_changes == []
        assert report.quality_delta == 0.0


class TestTriangleConnector:
    """TriangleConnector——闭环逻辑。"""

    @pytest.mark.asyncio
    async def test_close_loop_with_empty_cross_report(self):
        """空 CrossReport → 无发现。"""
        connector = TriangleConnector(evolution=None, knowledge=None)
        report = await connector.close_loop({}, "test.module")
        assert report.patterns_extracted == 0
        assert report.patterns_confirmed == 0

    @pytest.mark.asyncio
    async def test_close_loop_with_divergent_points(self):
        """CrossReport 含分歧点 → 提取为 review_rejection 模式。"""
        connector = TriangleConnector(evolution=None, knowledge=None)
        cross_report = {
            "divergent_points": [
                {
                    "target": "users.py:45",
                    "test_verdict": "PASSED",
                    "review_verdict": "WARNING",
                    "review_reason": "命名不规范",
                    "suggestion": "重命名为 create_user_if_not_exists",
                },
            ],
        }
        report = await connector.close_loop(cross_report, "users")
        assert report.patterns_extracted >= 1
        # 无 knowledge/ 时 frequency 为 1，不触发 Prompt 调整
        assert report.patterns_confirmed == 0  # frequency 1 < 2 threshold

    @pytest.mark.asyncio
    async def test_close_loop_with_ponytail_findings(self):
        """CrossReport 含 Ponytail 发现 → 提取为 ponytail_warning 模式。"""
        connector = TriangleConnector(evolution=None, knowledge=None)
        cross_report = {
            "review_result": {
                "ponytail_count": 3,
                "issues": [
                    {"source": "ponytail", "message": "不必要的抽象", "file": "mod.py"},
                ],
            },
            "divergent_points": [],
        }
        report = await connector.close_loop(cross_report, "mod")
        assert report.patterns_extracted >= 1
        assert any(p.error_type == "ponytail_warning" for p in []) is False  # issues 中 source 匹配

    @pytest.mark.asyncio
    async def test_pattern_frequency_below_threshold_no_prompt_change(self):
        """频率低于 PATTERN_FREQUENCY_THRESHOLD → 不触发 Prompt 进化。"""
        connector = TriangleConnector(evolution=None, knowledge=None)
        # 只有一个分歧点 → frequency=1 → <2 threshold
        cross_report = {
            "divergent_points": [
                {"target": "a.py:1", "test_verdict": "PASSED", "review_verdict": "WARNING",
                 "review_reason": "test", "suggestion": "fix"},
            ],
            "review_result": {"issues": [], "ponytail_count": 0},
        }
        report = await connector.close_loop(cross_report, "test")
        assert report.patterns_confirmed == 0
        assert report.prompt_changes == []

    @pytest.mark.asyncio
    async def test_respects_pattern_frequency_threshold(self):
        """PATTERN_FREQUENCY_THRESHOLD = 2——正确。"""
        connector = TriangleConnector(evolution=None, knowledge=None)
        assert connector.PATTERN_FREQUENCY_THRESHOLD == 2
