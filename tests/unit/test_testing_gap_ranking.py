"""graph/engines/test_gap_detector.py — M4 rank_by_risk 排序单元测试。"""

from __future__ import annotations

import pytest

from orbit.graph.engines.test_gap_detector import TestGap, TestGapDetector


class TestGapRiskRanking:
    """TestGapDetector.rank_by_risk()——M4 风险排序。"""

    @pytest.mark.asyncio
    async def test_rank_sorts_by_risk_score_descending(self):
        """按 risk_score 降序排列——高风险优先。"""
        detector = TestGapDetector()
        gaps = [
            TestGap(function_name="low_risk", param_name="x", param_type="int"),
            TestGap(function_name="high_risk", param_name="y", param_type="str"),
            TestGap(function_name="medium_risk", param_name="z", param_type="float"),
        ]
        # 手动设不同复杂度——模拟不同风险
        complexity = {"high_risk": 0.9, "medium_risk": 0.5, "low_risk": 0.1}
        ranked = await detector.rank_by_risk(gaps, code_graph=None, change_complexity=complexity)
        assert len(ranked) == 3
        # 高风险排第一
        assert ranked[0].function_name == "high_risk"
        assert ranked[0].risk_score > ranked[2].risk_score

    @pytest.mark.asyncio
    async def test_rank_with_static_issues_boosts_risk(self):
        """静态分析问题数高 → 风险分更高。"""
        detector = TestGapDetector()
        gaps = [
            TestGap(function_name="clean", param_name="x", param_type="int"),
            TestGap(function_name="messy", param_name="y", param_type="int"),
        ]
        complexity = {"clean": 0.5, "messy": 0.5}
        static_issues = {"clean": 0, "messy": 8}  # 8 个静态问题
        ranked = await detector.rank_by_risk(
            gaps, code_graph=None, change_complexity=complexity, static_issues=static_issues,
        )
        # messy 风险应更高（更多静态问题）
        assert ranked[0].function_name == "messy"

    @pytest.mark.asyncio
    async def test_rank_empty_list(self):
        """空列表 → 空列表。"""
        detector = TestGapDetector()
        ranked = await detector.rank_by_risk([], code_graph=None)
        assert ranked == []

    @pytest.mark.asyncio
    async def test_centrality_defaults_when_no_graph(self):
        """无 code_graph → centrality 默认 0.2。"""
        detector = TestGapDetector()
        gaps = [TestGap(function_name="f", param_name="x", param_type="int")]
        ranked = await detector.rank_by_risk(gaps, code_graph=None)
        assert ranked[0].centrality == 0.2

    @pytest.mark.asyncio
    async def test_risk_score_in_range(self):
        """risk_score 始终在 [0, 1] 范围内。"""
        detector = TestGapDetector()
        gaps = [TestGap(function_name="f", param_name="x", param_type="int")]
        complexity = {"f": 0.5}
        ranked = await detector.rank_by_risk(gaps, code_graph=None, change_complexity=complexity)
        assert 0.0 <= ranked[0].risk_score <= 1.0
