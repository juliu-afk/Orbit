# -*- coding: utf-8 -*-
"""RTS - regression test selection based on code graph dependency analysis.

WHY: Orbit has 45 modules. Running all unit tests takes 1+ min.
Don't run all tests when only one module changed - use code_graph
to find affected modules and only run their tests. Expect 60-80% time savings.

Ref: Google Speculative Testing (-65% detection time) / Ekstazi (Apache).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TestSelector:
    """Select tests affected by code changes using code_graph dependency info.

    Input: list of changed source files
    Output: list of test files to execute
    """
    __test__ = False  # not a pytest test class

    def __init__(self, code_graph=None):
        self._code_graph = code_graph

    async def select(
        self,
        changed_files: list[str],
        all_tests: list[str] | None = None,
    ) -> list[str]:
        """Select test files affected by the given changed source files.

        Args:
            changed_files: e.g. ["src/orbit/scheduler/state_machine.py"]
            all_tests: full test file list (scans tests/ dir if None)

        Returns:
            test file paths to execute
        """
        if not changed_files:
            return all_tests or []

        # 1. extract affected modules from changed files
        affected_modules: set[str] = set()
        for f in changed_files:
            module = self._file_to_module(f)
            if module:
                affected_modules.add(module)

        if not affected_modules:
            return all_tests or []

        # 2. expand via code_graph callers/callees
        if self._code_graph:
            expanded = await self._expand_affected(affected_modules)
            affected_modules.update(expanded)

        # 3. map affected modules to test files
        selected = self._map_modules_to_tests(affected_modules, all_tests)

        logger.info(
            "rts_selection",
            changed=len(changed_files),
            affected_modules=len(affected_modules),
            selected_tests=len(selected),
            total_tests=len(all_tests) if all_tests else "unknown",
        )
        return selected

    async def _expand_affected(self, modules: set[str]) -> set[str]:
        """Expand affected set via code_graph callers and callees."""
        expanded: set[str] = set()
        for module in modules:
            try:
                callers = await self._code_graph.get_callers(module)
                for caller in callers:
                    caller_module = self._symbol_to_module(caller)
                    if caller_module:
                        expanded.add(caller_module)

                callees = await self._code_graph.get_callees(module)
                for callee in callees:
                    callee_module = self._symbol_to_module(callee)
                    if callee_module:
                        expanded.add(callee_module)
            except Exception:
                logger.debug("rts_expand_failed", module=module, exc_info=True)
        return expanded

    def _file_to_module(self, file_path: str) -> str | None:
        """Convert file path to module name.

        src/orbit/scheduler/state_machine.py -> scheduler.state_machine
        """
        p = Path(file_path)
        path_str = p.as_posix()  # normalize to forward slashes on Windows
        if "src/orbit/" not in path_str and not path_str.startswith("orbit/"):
            return None
        parts = p.parts
        try:
            orbit_idx = next(i for i, part in enumerate(parts) if part == "orbit")
            module_parts = list(parts[orbit_idx + 1:])
            if module_parts and module_parts[-1].endswith(".py"):
                module_parts[-1] = module_parts[-1][:-3]
            return ".".join(module_parts)
        except (StopIteration, IndexError):
            return None

    def _symbol_to_module(self, symbol_name: str) -> str | None:
        """Convert symbol name to module name.

        scheduler.state_machine.transition -> scheduler.state_machine
        """
        parts = symbol_name.split(".")
        if len(parts) >= 2:
            return ".".join(parts[:-1])
        return parts[0] if parts else None

    def _map_modules_to_tests(
        self,
        modules: set[str],
        all_tests: list[str] | None,
    ) -> list[str]:
        """Map affected modules to corresponding test files.

        Rule: module name keyword must appear in test file name.
        """
        if not all_tests:
            test_root = Path("tests")
            if test_root.exists():
                all_tests = [
                    str(p) for p in test_root.rglob("test_*.py")
                    if "__pycache__" not in str(p)
                ]

        selected: set[str] = set()
        for test_file in (all_tests or []):
            test_name = Path(test_file).stem
            for module in modules:
                parts = module.split(".")
                # match any module part against test filename
                if any(part in test_name for part in parts):
                    selected.add(test_file)
                    break
                # also match full module path with underscores
                if module.replace(".", "_") in test_name:
                    selected.add(test_file)
                    break

        return sorted(selected)
