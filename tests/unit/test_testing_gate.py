"""testing/gate.py 单元测试。"""

from __future__ import annotations

import pytest

from orbit.testing.gate import GateDecision, QualityGate, TestRunResult


class TestQualityGate:
    """QualityGate.evaluate() 的判定逻辑。"""

    def test_passed_when_all_ok(self):
        """全部指标达标 → PASSED。"""
        gate = QualityGate()
        result = TestRunResult(
            task_id="t1",
            compiled=True,
            coverage_pct=0.85,
            mutation_score=0.75,
            passed=10,
            status="passed",
        )
        assert gate.evaluate(result) == GateDecision.PASSED

    def test_failed_when_not_compiled(self):
        """编译失败 → FAILED。"""
        gate = QualityGate()
        result = TestRunResult(compiled=False)
        assert gate.evaluate(result) == GateDecision.FAILED

    def test_failed_when_critical_vulnerability(self):
        """安全漏洞 → FAILED。"""
        gate = QualityGate()
        result = TestRunResult(compiled=True, critical_vulnerabilities=1)
        assert gate.evaluate(result) == GateDecision.FAILED

    def test_failed_when_framework_blocking(self):
        """循环依赖 → FAILED。"""
        gate = QualityGate()
        result = TestRunResult(
            compiled=True,
            framework_blockings=["circular: A → B → A"],
        )
        assert gate.evaluate(result) == GateDecision.FAILED

    def test_supplement_when_low_coverage(self):
        """覆盖率 < 80% → SUPPLEMENT。"""
        gate = QualityGate()
        result = TestRunResult(compiled=True, coverage_pct=0.55)
        assert gate.evaluate(result) == GateDecision.SUPPLEMENT

    def test_supplement_when_low_mutation_score(self):
        """变异评分 < 70% → SUPPLEMENT。"""
        gate = QualityGate()
        result = TestRunResult(
            compiled=True,
            coverage_pct=0.85,
            mutation_score=0.50,
        )
        assert gate.evaluate(result) == GateDecision.SUPPLEMENT

    def test_no_supplement_when_mutation_score_is_none(self):
        """非核心模块（mutation_score=None）→ 不检查变异评分。"""
        gate = QualityGate()
        result = TestRunResult(
            compiled=True,
            coverage_pct=0.85,
            mutation_score=None,
        )
        assert gate.evaluate(result) == GateDecision.PASSED

    def test_failed_permanent_after_max_repairs(self):
        """修复 3 轮 → FAILED_PERMANENT。"""
        gate = QualityGate()
        result = TestRunResult(
            compiled=False,
            repair_attempts=3,
        )
        assert gate.evaluate(result) == GateDecision.FAILED_PERMANENT

    def test_describe_passed(self):
        """描述——PASSED。"""
        gate = QualityGate()
        result = TestRunResult(compiled=True, coverage_pct=0.90, passed=5)
        desc = gate.describe(result)
        assert "通过" in desc

    def test_describe_failed_with_reasons(self):
        """描述——FAILED 含具体原因。"""
        gate = QualityGate()
        result = TestRunResult(compiled=False, critical_vulnerabilities=2)
        desc = gate.describe(result)
        assert "编译失败" in desc
        assert "2" in desc

    def test_describe_supplement_with_gaps(self):
        """描述——SUPPLEMENT 含覆盖率缺口信息。"""
        gate = QualityGate()
        result = TestRunResult(compiled=True, coverage_pct=0.60)
        desc = gate.describe(result)
        assert "覆盖率" in desc


class TestTestRunResult:
    """TestRunResult 数据载体。"""

    def test_defaults(self):
        """默认值正确。"""
        r = TestRunResult()
        assert r.passed == 0
        assert r.compiled is True
        assert r.repair_attempts == 0

    def test_errors_accumulate(self):
        """错误列表可追加。"""
        r = TestRunResult()
        r.errors.append("timeout")
        r.errors.append("import error")
        assert len(r.errors) == 2
