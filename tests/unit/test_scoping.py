"""测试 _decide_test_scope + scanners (PR#201 P1-3)."""
from __future__ import annotations

import pytest

# Import module-level function directly
from orbit.scheduler.task_runner.context import _decide_test_scope


class TestDecideTestScope:
    """v2: 简化版 _decide_test_scope——基于文件数而非模块敏感度。"""

    def test_empty_returns_unit_only(self):
        assert _decide_test_scope({}) == "unit_only"

    def test_no_changes_returns_unit_only(self):
        assert _decide_test_scope({"changed": [], "added": []}) == "unit_only"

    def test_few_files_returns_unit_integration(self):
        assert _decide_test_scope({
            "changed": ["a.py", "b.py"],
            "added": [],
            "total": 2,
        }) == "unit_integration"

    def test_many_files_returns_unit_integration_e2e(self):
        assert _decide_test_scope({
            "changed": ["a.py", "b.py", "c.py", "d.py"],
            "added": ["e.py"],
            "total": 5,
        }) == "unit_integration_e2e"


class TestAffectedFilesScanner:
    def test_creates_instance(self):
        from orbit.context.scanners.affected_files import AffectedFilesScanner
        s = AffectedFilesScanner()
        assert s.name == "affected_files"
        result = s.scan(".")
        assert "changed" in result
        assert "total" in result


class TestImportDependencyScanner:
    def test_creates_instance(self):
        from orbit.context.scanners.import_deps import ImportDependencyScanner
        s = ImportDependencyScanner()
        assert s.name == "import_deps"

    def test_scan_empty_returns_empty(self):
        from orbit.context.scanners.import_deps import ImportDependencyScanner
        s = ImportDependencyScanner()
        result = s.scan(".")
        assert result["language"] == "python"
        assert result["imports_by_file"] == {}
