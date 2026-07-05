"""Create all Orbit context Phase 2 files with PR#201 review fixes baked in."""
import os, textwrap

BASE = 'src/orbit/context'

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(textwrap.dedent(content).lstrip())
    print(f'  OK: {path}')

# ── scanners ──
w(f'{BASE}/scanners/test_coverage.py', '''
"""coverage.json → 覆盖率缺口."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

class TestCoverageScanner(BaseScanner):
    name = "test_coverage"
    def scan(self, project_path: str, affected_files: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"gaps": [], "overall_coverage": 0.0, "files_under_threshold": []}
        root = Path(project_path)
        coverage_path = root / "coverage.json"
        if not coverage_path.exists():
            return {**result, "note": "coverage.json not found"}
        try:
            data = json.loads(coverage_path.read_text(encoding="utf-8"))
            summary = data.get("totals", {})
            result["overall_coverage"] = summary.get("percent_covered", 0.0)
            target_files = set(affected_files or [])
            for file_path, file_info in data.get("files", {}).items():
                pct = file_info.get("summary", {}).get("percent_covered", 100.0)
                if pct < 80.0 and (not target_files or file_path in target_files):
                    missing = file_info.get("missing_lines", [])
                    result["gaps"].append({"file": file_path, "coverage_pct": pct, "missing_lines": missing[:20]})
                    result["files_under_threshold"].append(file_path)
            return result
        except (json.JSONDecodeError, OSError, KeyError) as e:
            return {**result, "error": str(e)}
''')

w(f'{BASE}/scanners/schema_change.py', '''
"""Alembic → 表/列变更. PR#201 P2-4: 读所有迁移文件."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

class SchemaChangeScanner(BaseScanner):
    name = "schema_change"
    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"tables_added": [], "tables_modified": [], "columns_added": [], "has_migration": False}
        root = Path(project_path)
        candidates = [root / "alembic" / "versions", root / "migrations", root / "backend" / "alembic" / "versions"]
        migrations_dir = None
        for c in candidates:
            if c.exists() and c.is_dir():
                migrations_dir = c
                break
        if migrations_dir is None:
            return {**result, "note": "no migration directory found"}
        try:
            py_files = sorted(migrations_dir.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not py_files:
                return result
            result["has_migration"] = True
            create_tables, alter_tables, add_columns = [], [], []
            for migration_file in py_files[:10]:
                content = migration_file.read_text(encoding="utf-8", errors="replace")
                create_tables.extend(re.findall(r"create_table\s*\(\s*[\"']([^\"']+)[\"']", content, re.IGNORECASE))
                alter_tables.extend(re.findall(r"alter_table\s*\(\s*[\"']([^\"']+)[\"']", content, re.IGNORECASE))
                add_columns.extend(
                    {"table": t, "column": c}
                    for t, c in re.findall(r"add_column\s*\(\s*[\"']([^\"']+)[\"']\s*,\s*sa\.Column\s*\(\s*[\"']([^\"']+)[\"']", content, re.IGNORECASE)
                )
            result["tables_added"] = create_tables
            result["tables_modified"] = alter_tables
            result["columns_added"] = add_columns
            return result
        except OSError as e:
            return {**result, "error": str(e)}
''')

w(f'{BASE}/scanners/permission_string.py', '''
"""正则 → 权限字符串比对."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

_PERMISSION_PATTERN = re.compile(r"(?:require|has|check)_permission\s*\(\s*[\"']([^\"']+)[\"']")

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
                            rel_path = str(py_file.relative_to(root)).replace("\\\\", "/")
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
                strings = re.findall(r'"([^"]+)"', content)
                known.update(s for s in strings if ":" in s)
            except (UnicodeDecodeError, OSError):
                pass
        return known
''')

w(f'{BASE}/scanners/__init__.py', '''
"""确定性预扫描器——不用LLM，纯规则/AST/git."""
from orbit.context.scanners.affected_files import AffectedFilesScanner
from orbit.context.scanners.import_deps import ImportDependencyScanner
from orbit.context.scanners.test_coverage import TestCoverageScanner
from orbit.context.scanners.schema_change import SchemaChangeScanner
from orbit.context.scanners.permission_string import PermissionStringScanner
__all__ = ["AffectedFilesScanner", "ImportDependencyScanner", "TestCoverageScanner", "SchemaChangeScanner", "PermissionStringScanner"]
''')

print("Scanners done")
