"""testing/redundancy_check.py 单元测试。"""

from __future__ import annotations

import pytest

from orbit.testing.redundancy_check import (
    FrameworkFitReport,
    FrameworkIssue,
    IssueSeverity,
    IssueType,
    RedundancyChecker,
)


class TestFrameworkFitReport:
    """FrameworkFitReport 数据结构。"""

    def test_empty_report_has_no_blockings(self):
        r = FrameworkFitReport()
        assert r.has_blockings is False
        assert r.total_issues == 0

    def test_report_with_blockings(self):
        r = FrameworkFitReport(
            blockings=[FrameworkIssue(
                severity=IssueSeverity.BLOCKING,
                type=IssueType.CIRCULAR_DEP,
                detail="A → B → A",
            )],
        )
        assert r.has_blockings is True
        assert r.total_issues == 1

    def test_mixed_report(self):
        r = FrameworkFitReport(
            blockings=[FrameworkIssue(IssueSeverity.BLOCKING, IssueType.CIRCULAR_DEP, "环")],
            warnings=[FrameworkIssue(IssueSeverity.WARNING, IssueType.NAME_CONFLICT, "同名")],
            infos=[FrameworkIssue(IssueSeverity.INFO, IssueType.IMPORT_REDUNDANT, "冗余")],
        )
        assert r.total_issues == 3


class TestRedundancyChecker:
    """RedundancyChecker 框架适配检查。"""

    def test_layer_violation_api_calls_graph(self):
        """API 层直接 import graph → 警告。"""
        checker = RedundancyChecker()
        code = "from orbit.graph.engines.code_graph import CodeGraph"
        # 模拟 module 路径含 "api"
        issues = checker._check_layer_violations(code, "src/orbit/api/v1/test_routes.py")

        assert len(issues) >= 1
        assert issues[0].severity == IssueSeverity.WARNING
        assert issues[0].type == IssueType.LAYER_VIOLATION

    def test_layer_violation_model_imports_api(self):
        """Model 层反向 import API → 警告。"""
        checker = RedundancyChecker()
        code = "from orbit.api.v1.users import router"
        issues = checker._check_layer_violations(code, "src/orbit/models/user.py")

        assert len(issues) >= 1
        assert issues[0].severity == IssueSeverity.WARNING

    def test_no_violation_service_imports_model(self):
        """Service 层 import model → 无警告（合理调用）。"""
        checker = RedundancyChecker()
        code = "from orbit.models.user import User"
        issues = checker._check_layer_violations(code, "src/orbit/services/user_service.py")

        assert len(issues) == 0

    def test_non_standard_path_skipped(self):
        """非标准路径 → 跳过分层检查。"""
        checker = RedundancyChecker()
        code = "from orbit.api.v1.test_routes import router"
        issues = checker._check_layer_violations(code, "tests/unit/test_something.py")

        assert len(issues) == 0

    def test_check_circular_dep_no_codegraph(self):
        """无 code_graph → 不报循环依赖（不崩溃）。"""
        checker = RedundancyChecker()
        code = "from orbit.scheduler import DAG"
        # 同步调用——无 code_graph 时返回空
        import asyncio
        issues = asyncio.run(checker._check_circular_dep("loop.runner", code))
        assert issues == []  # 无 code_graph → 无法检测 → 不误报

    def test_check_name_conflicts_no_codegraph(self):
        """无 code_graph → 不报同名冲突（不崩溃）。"""
        checker = RedundancyChecker()
        code = "def create_user(): pass"
        import asyncio
        issues = asyncio.run(checker._check_name_conflicts(code, "users"))
        assert issues == []  # 无 code_graph → 不检测 → 不误报

    def test_check_semantic_duplicates_no_knowledge(self):
        """无 knowledge → 返回空（不崩溃）。"""
        checker = RedundancyChecker()
        import asyncio
        issues = asyncio.run(checker._check_semantic_duplicates("code", "mod"))
        assert issues == []
