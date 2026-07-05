"""Python import 依赖扫描器——AST 解析 import 语句.

只用 Python AST——不用 LLM。非 Python 项目跳过。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from orbit.context.scanners.base import BaseScanner


class ImportDependencyScanner(BaseScanner):
    """Python AST → 受影响文件的 import 依赖图。

    输出: {
        "language": "python" | "unsupported",
        "imports_by_file": {"src/orbit/agents/react_agent.py": ["structlog", "orbit.agents.base", ...]},
        "affected_modules": ["orbit.agents", "orbit.compression", ...],
        "cross_module_deps": {"agents": ["compression", "gateway"], ...}
    }
    """

    name = "import_deps"

    def scan(self, project_path: str, affected_files: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "language": "python",
            "imports_by_file": {},
            "affected_modules": [],
            "cross_module_deps": {},
        }

        files = affected_files or []
        if not files:
            return result

        root = Path(project_path)
        # 只处理 Python 文件
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

            # 提取受影响模块
            modules = set()
            for imports in result["imports_by_file"].values():
                for imp in imports:
                    # orbit.xxx 开头的内部模块
                    if imp.startswith("orbit."):
                        parts = imp.split(".")
                        if len(parts) >= 2:
                            modules.add(parts[1])  # 二级模块名
            result["affected_modules"] = sorted(modules)

            # 跨模块依赖
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
        """从 Python 文件提取 import 列表——AST 解析。

        WHY AST 而非正则: 正则无法正确处理多行 import、注释中的 import、字符串中的 import。
        """
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
