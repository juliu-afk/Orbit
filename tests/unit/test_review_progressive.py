"""review/progressive.py 单元测试——渐进式审查引擎。"""

from __future__ import annotations

import pytest

from orbit.review.progressive import (
    CheckpointVerdict,
    ProgressiveReviewEngine,
    ProgressiveReviewReport,
    ReviewCheckpoint,
)


class TestReviewCheckpoint:
    """ReviewCheckpoint 数据模型——三列对照。"""

    def test_default_verdict_is_not_found(self):
        """新检查点默认判定为 NOT_FOUND。"""
        cp = ReviewCheckpoint(id="test", expectation="something")
        assert cp.verdict == CheckpointVerdict.NOT_FOUND

    def test_default_severity_is_major(self):
        """默认严重度为 major。"""
        cp = ReviewCheckpoint(id="test")
        assert cp.severity == "major"

    def test_all_fields_populated(self):
        """所有字段可填充——三列完整。"""
        cp = ReviewCheckpoint(
            id="sig_task1",
            source_phase="spec",
            source_ref="Task task1 — signature",
            expectation="def create_user(name: str) -> User",
            adr_constraint="使用 SQLAlchemy 2.0 Mapped 风格",
            actual_location="services/users.py:42",
            actual_snippet="def create_user(name: str) -> User:",
            verdict=CheckpointVerdict.MATCH,
            evidence="函数签名完全匹配",
            severity="critical",
            task_id="task1",
        )
        assert cp.verdict == CheckpointVerdict.MATCH
        assert cp.source_phase == "spec"
        assert cp.actual_location == "services/users.py:42"


class TestProgressiveReviewReport:
    """ProgressiveReviewReport 统计方法。"""

    def test_empty_report_has_full_match_rate(self):
        """空报告——match_rate = 1.0。"""
        report = ProgressiveReviewReport()
        assert report.match_rate == 1.0
        assert report.matched == 0
        assert report.high_severity_gaps == []

    def test_match_rate_calculation(self):
        """match_rate = matched / total。"""
        report = ProgressiveReviewReport(checkpoints=[
            ReviewCheckpoint(id="1", verdict=CheckpointVerdict.MATCH),
            ReviewCheckpoint(id="2", verdict=CheckpointVerdict.MATCH),
            ReviewCheckpoint(id="3", verdict=CheckpointVerdict.DEVIATION),
        ])
        assert report.match_rate == 2 / 3
        assert report.matched == 2
        assert report.deviations == 1

    def test_high_severity_gaps_filters_correctly(self):
        """只返回 DEVIATION 或 NOT_FOUND + severity≥major 的检查点。"""
        report = ProgressiveReviewReport(checkpoints=[
            ReviewCheckpoint(id="1", verdict=CheckpointVerdict.DEVIATION, severity="critical"),
            ReviewCheckpoint(id="2", verdict=CheckpointVerdict.NOT_FOUND, severity="major"),
            ReviewCheckpoint(id="3", verdict=CheckpointVerdict.DEVIATION, severity="minor"),
            ReviewCheckpoint(id="4", verdict=CheckpointVerdict.MATCH, severity="critical"),
        ])
        gaps = report.high_severity_gaps
        assert len(gaps) == 2
        assert gaps[0].id == "1"
        assert gaps[1].id == "2"


class TestProgressiveReviewEngine:
    """ProgressiveReviewEngine——构建 + 填充。"""

    # ── 辅助：创建模拟 Spec ──

    @staticmethod
    def _make_mock_spec(title="test", tasks=None):
        """创建模拟 Spec 对象——避免导入 compose.models 的依赖链。"""
        class MockTask:
            def __init__(self, id, description="", signature="", behavior=None, tests=None):
                self.id = id
                self.description = description
                self.signature = signature
                self.behavior = behavior or []
                self.tests = tests or []

        class MockSpec:
            def __init__(self):
                self.title = title
                self.tasks = tasks or []

        spec = MockSpec()
        spec.tasks = [MockTask(**t) if isinstance(t, dict) else t for t in (tasks or [])]
        return spec

    def test_build_from_empty_spec(self):
        """空 Spec → 空报告。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[])
        report = engine.build_from_spec(spec)
        assert len(report.checkpoints) == 0
        assert report.phase == "prd"

    def test_build_from_spec_with_signature(self):
        """Task 有 signature → 生成接口检查点。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "signature": "async def create_user(db: AsyncSession, data: UserCreate) -> User"},
        ])
        report = engine.build_from_spec(spec)
        assert len(report.checkpoints) == 1
        assert report.checkpoints[0].source_phase == "spec"
        assert "create_user" in report.checkpoints[0].expectation
        assert report.checkpoints[0].severity == "critical"

    def test_build_from_spec_with_behaviors(self):
        """Task 有 behavior → 每个 behavior 一个检查点。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "behavior": [
                "WHEN email 已存在 THEN raise DuplicateError",
                "WHEN name 为空 THEN raise ValueError",
            ]},
        ])
        report = engine.build_from_spec(spec)
        assert len(report.checkpoints) == 2
        assert all(cp.severity == "major" for cp in report.checkpoints)
        assert "DuplicateError" in report.checkpoints[0].expectation

    def test_build_from_spec_empty_task_gets_description_checkpoint(self):
        """Task 无 signature/behavior/tests → 回退 description 检查点。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "description": "实现用户登录功能"},
        ])
        report = engine.build_from_spec(spec)
        assert len(report.checkpoints) == 1
        assert report.checkpoints[0].source_phase == "spec"
        assert "用户登录" in report.checkpoints[0].expectation

    def test_build_from_spec_with_tests(self):
        """Task 有 tests → 每个测试断言一个检查点。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "tests": ["assert result.status == 200", "assert result.data.name == 'test'"]},
        ])
        report = engine.build_from_spec(spec)
        assert len(report.checkpoints) == 2
        assert "测试断言" in report.checkpoints[0].expectation

    def test_build_from_prd_text(self):
        """PRD 文本含验收标准 → 提取为检查点。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "description": "dummy"},
        ])
        prd_text = """
        ## 验收标准
        - 用户上传 CSV 后 5 秒内看到预览
        - 所有 API 端点需认证
        * 转账金额使用 Decimal
        """
        report = engine.build_from_spec(spec, prd_text=prd_text)
        # t1 description 1 个 + prd 3 个 = 4
        assert len(report.checkpoints) == 4
        prd_checkpoints = [c for c in report.checkpoints if c.source_phase == "prd"]
        assert len(prd_checkpoints) == 3

    def test_build_with_adr_text(self):
        """ADR 文本 → 填充已有检查点的中列。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "signature": "使用 SQLAlchemy 2.0 Mapped 风格进行 ORM 建模"},
        ])
        adr_text = "使用 SQLAlchemy 2.0 Mapped 风格进行 ORM 建模。"
        report = engine.build_from_spec(spec, adr_text=adr_text)
        # adr_constraint 被填充到 signature 检查点——关键词 "SQLAlchemy" 匹配
        assert report.checkpoints[0].adr_constraint != ""

    def test_fill_code_column_match(self):
        """代码输出包含预期关键词 → MATCH。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "signature": "def create_user"},
        ])
        report = engine.build_from_spec(spec)
        task_results = {"t1": {"output": "def create_user(name: str) -> User:\n    ...", "status": "ok"}}
        report = engine.fill_code_column(report, task_results)
        assert report.checkpoints[0].verdict == CheckpointVerdict.MATCH

    def test_fill_code_column_not_found(self):
        """任务失败 → NOT_FOUND。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "signature": "def create_user"},
        ])
        report = engine.build_from_spec(spec)
        task_results = {"t1": {"output": "", "status": "error", "error": "something broke"}}
        report = engine.fill_code_column(report, task_results)
        assert report.checkpoints[0].verdict == CheckpointVerdict.NOT_FOUND

    def test_fill_code_column_task_not_in_results(self):
        """Task 不在 results 中 → NOT_FOUND。"""
        engine = ProgressiveReviewEngine()
        spec = self._make_mock_spec(tasks=[
            {"id": "t1", "signature": "def create_user"},
        ])
        report = engine.build_from_spec(spec)
        report = engine.fill_code_column(report, {})
        assert report.checkpoints[0].verdict == CheckpointVerdict.NOT_FOUND

    def test_keyword_extraction(self):
        """关键字提取——英文标识符 + 中文词。"""
        keywords = ProgressiveReviewEngine._extract_keywords(
            "函数签名: async def create_user 用户登录功能"
        )
        assert "create_user" in keywords
        assert "async" in keywords
        assert "def" in keywords
        # 中文词提取
        assert "用户登录" in keywords or "用户" in keywords
