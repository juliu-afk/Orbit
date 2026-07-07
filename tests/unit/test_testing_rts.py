"""testing/rts.py 单元测试。"""

from __future__ import annotations

from pathlib import Path

from orbit.testing.rts import TestSelector


class TestFileToModule:
    def test_orbit_source_file(self):
        ts = TestSelector()
        assert ts._file_to_module("src/orbit/scheduler/state_machine.py") == "scheduler.state_machine"

    def test_orbit_api_file(self):
        ts = TestSelector()
        assert ts._file_to_module("src/orbit/api/routes/users.py") == "api.routes.users"

    def test_non_orbit_file_returns_none(self):
        ts = TestSelector()
        assert ts._file_to_module("tests/unit/test_foo.py") is None

    def test_empty_list_returns_all_tests(self):
        ts = TestSelector()
        all_tests = ["tests/unit/test_a.py", "tests/unit/test_b.py"]
        import asyncio
        result = asyncio.run(ts.select([], all_tests))
        assert result == all_tests


class TestMapModulesToTests:
    def test_direct_match(self):
        ts = TestSelector()
        selected = ts._map_modules_to_tests(
            {"scheduler.state_machine"},
            ["tests/unit/test_scheduler.py", "tests/unit/test_gateway.py"],
        )
        assert "tests/unit/test_scheduler.py" in selected
        assert "tests/unit/test_gateway.py" not in selected

    def test_partial_module_match(self):
        ts = TestSelector()
        selected = ts._map_modules_to_tests(
            {"api.routes.users"},
            ["tests/integration/test_users_api.py", "tests/unit/test_gate.py"],
        )
        assert "tests/integration/test_users_api.py" in selected

    def test_empty_modules_returns_none_selected(self):
        ts = TestSelector()
        selected = ts._map_modules_to_tests(set(), ["tests/unit/test_a.py"])
        assert selected == []


class TestSymbolToModule:
    def test_function_to_module(self):
        ts = TestSelector()
        assert ts._symbol_to_module("scheduler.state_machine.transition") == "scheduler.state_machine"

    def test_single_segment_returns_itself(self):
        ts = TestSelector()
        assert ts._symbol_to_module("utils") == "utils"
