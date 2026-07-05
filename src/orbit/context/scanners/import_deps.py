"""Python AST → import 依赖图."""
from __future__ import annotations
import ast
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

class ImportDependencyScanner(BaseScanner):
    name = "import_deps"
    def scan(self, project_path: str, affected_files: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"language": "python", "imports_by_file": {}, "affected_modules": [], "cross_module_deps": {}}
        files = affected_files or []
        if not files:
            return result
        root = Path(project_path)
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            return result
        try:
            for rel_path in py_files:
                full_path = root / rel_path
                if not full_path.exists():
                    continue
                imports = self._extract_imports(full_path)
                if imports:
                    result["imports_by_file"][rel_path] = imports
            modules = set()
            for imports in result["imports_by_file"].values():
                for imp in imports:
                    if imp.startswith("orbit."):
                        parts = imp.split(".")
                        if len(parts) >= 2:
                            modules.add(parts[1])
            result["affected_modules"] = sorted(modules)
            cross: dict[str, list[str]] = {}
            for rel_path, imports in result["imports_by_file"].items():
                file_module = rel_path.split("/")[1] if "/" in rel_path else "root"
                orbit_imports = [i for i in imports if i.startswith("orbit.")]
                if orbit_imports:
                    cross[file_module] = orbit_imports
            result["cross_module_deps"] = cross
            return result
        except Exception as e:
            return {**result, "error": str(e)}
    @staticmethod
    def _extract_imports(file_path: Path) -> list[str]:
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            return imports
        except (SyntaxError, UnicodeDecodeError, OSError):
            return []
