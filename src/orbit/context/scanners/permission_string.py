"""正则 → 权限字符串比对."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

_PERMISSION_PATTERN = re.compile(r"(?:require|has|check)_permission\s*\(\s*'([^']+)'")


class PermissionStringScanner(BaseScanner):
    name = "permission_string"
    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"permissions_found": [], "unregistered": [], "total": 0}
        root = Path(project_path)
        known = self._collect_known_permissions(root)
        try:
            src_dir = root / "src"
            if not src_dir.exists():
                src_dir = root
            for py_file in src_dir.rglob("*.py"):
                if "__pycache__" in str(py_file) or ".venv" in str(py_file):
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    for lineno, line in enumerate(content.splitlines(), 1):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        for perm in _PERMISSION_PATTERN.findall(line):
                            rel_path = str(py_file.relative_to(root)).replace("\\", "/")
                            entry = {"file": rel_path, "line": lineno, "permission": perm}
                            result["permissions_found"].append(entry)
                            if known and perm not in known:
                                result["unregistered"].append(entry)
                except (UnicodeDecodeError, OSError):
                    continue
            result["total"] = len(result["permissions_found"])
            if not known:
                result["note"] = "no rbac registry found"
            return result
        except Exception as e:
            return {**result, "error": str(e)}
    @staticmethod
    def _collect_known_permissions(root: Path) -> set[str]:
        known: set[str] = set()
        for f in list(root.rglob("rbac.py")) + list(root.rglob("permissions.py"))[:3]:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                strings = re.findall(r"'([^']+)'", content)
                known.update(s for s in strings if ":" in s)
            except (UnicodeDecodeError, OSError):
                pass
        return known
