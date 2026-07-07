"""testing/reporter.py 单元测试。"""

from __future__ import annotations

from orbit.testing.gate import GateDecision, TestRunResult
from orbit.testing.redundancy_check import FrameworkFitReport
from orbit.testing.reporter import CrossReport, TestReporter


class TestTestReporter:
    """TestReporter 生成各类报告。"""

    def test_build_summary_card_passed(self):
        """通过场景——摘要卡片含基本信息。"""
        reporter = TestReporter()
        result = TestRunResult(
            task_id="t1",
            compiled=True,
            coverage_pct=0.89,
            passed=12,
            failed=0,
            skipped=2,
            duration_sec=3.2,
        )
        card = reporter.build_summary_card(result, GateDecision.PASSED)
        assert card["type"] == "test_result"
        assert card["summary"]["passed"] == 12
        assert card["summary"]["coverage_pct"] == 89
        assert card["verdict"] == "passed"
        assert card["verdict_color"] == "green"

    def test_build_summary_card_failed(self):
        """失败场景——摘要卡片含错误信息。"""
        reporter = TestReporter()
        result = TestRunResult(
            task_id="t2",
            compiled=False,
            failed=1,
            errors=["NameError: name 'x' is not defined"],
        )
        card = reporter.build_summary_card(result, GateDecision.FAILED)
        assert card["verdict"] == "failed"
        assert card["verdict_color"] == "red"
        assert len(card["errors"]) == 1

    def test_build_summary_card_with_framework_warnings(self):
        """框架警告附加到摘要卡片。"""
        reporter = TestReporter()
        result = TestRunResult(task_id="t3", compiled=True, coverage_pct=0.85)
        framework = FrameworkFitReport(
            warnings=[],  # 由 RedundancyChecker 生成，此处空
        )
        card = reporter.build_summary_card(result, GateDecision.PASSED, framework)
        assert card["framework_warnings"] == []

    def test_build_cross_report_test_only(self):
        """无审查结果 → consensus=test_only。"""
        reporter = TestReporter()
        result = TestRunResult(task_id="t4", compiled=True, coverage_pct=0.90)
        cross = reporter.build_cross_report("t4", result)

        assert cross.consensus == "test_only"
        assert len(cross.divergent_points) == 0

    def test_build_cross_report_aligned(self):
        """审查无 issue → consensus=aligned。"""
        reporter = TestReporter()
        result = TestRunResult(task_id="t5", compiled=True, failed=0, passed=5)
        review = {"issues": []}
        cross = reporter.build_cross_report("t5", result, review)

        assert cross.consensus == "aligned"

    def test_build_cross_report_divergent_with_blocking_review(self):
        """审查 blocking → 分歧。"""
        reporter = TestReporter()
        result = TestRunResult(task_id="t6", compiled=True, failed=0)
        review = {
            "issues": [{
                "file": "users.py",
                "line": 42,
                "severity": "blocking",
                "message": "SQL injection risk",
                "suggestion": "Use parameterized query",
            }],
        }
        cross = reporter.build_cross_report("t6", result, review)

        assert cross.consensus == "divergent"
        assert len(cross.divergent_points) == 1
        assert "SQL injection" in cross.divergent_points[0].review_reason

    def test_build_detail_panel_includes_cases(self):
        """详情面板含用例列表。"""
        reporter = TestReporter()
        result = TestRunResult(task_id="t7", compiled=True)
        detail = reporter.build_detail_panel(
            result,
            GateDecision.PASSED,
            cases=[{"name": "test_add", "status": "passed", "duration": 0.1}],
        )
        assert len(detail["cases"]) == 1
