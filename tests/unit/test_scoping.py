"""测试 _decide_test_scope + scanners (PR#201 P1-3)."""
from __future__ import annotations

import pytest

# Import module-level function directly
from orbit.scheduler.task_runner import _decide_test_scope


class TestDecideTestScope:
    def test_empty_files_returns_smoke(self):
        assert _decide_test_scope({"changed": [], "added": []}) == "smoke"

    def test_frontend_only_returns_smoke(self):
        assert _decide_test_scope({
            "changed": ["frontend/src/App.vue", "frontend/src/views/Dashboard.vue"],
            "added": [],
        }) == "smoke"

    def test_core_module_returns_full_regression(self):
        assert _decide_test_scope({
            "changed": ["src/orbit/agents/react_agent.py"],
            "added": [],
        }) == "full_regression"

        assert _decide_test_scope({
            "changed": ["src/orbit/scheduler/orchestrator.py"],
            "added": [],
        }) == "full_regression"

        assert _decide_test_scope({
            "changed": ["src/orbit/gateway/client.py"],
            "added": [],
        }) == "full_regression"

        assert _decide_test_scope({
            "changed": ["frontend/src/App.vue", "src/orbit/hallucination/entropy.py"],
            "added": [],
        }) == "full_regression"

    def test_backend_returns_unit_integration(self):
        assert _decide_test_scope({
            "changed": ["src/orbit/api/routes/task.py", "src/orbit/memory/store.py"],
            "added": [],
        }) == "unit_integration"

    def test_mixed_non_core_returns_unit_integration(self):
        assert _decide_test_scope({
            "changed": ["frontend/src/App.vue", "src/orbit/tools/registry.py"],
            "added": [],
        }) == "unit_integration"

    def test_empty_affected_dict(self):
        assert _decide_test_scope({}) == "smoke"


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
