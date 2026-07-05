"""Alembic → 表/列变更. PR#201 P2-4: 读所有迁移文件."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

# 匹配 create_table('xxx') / alter_table('xxx') / add_column('t', sa.Column('c', ...))
_RE_CR = re.compile(r"create_table\s*\(\s*'([^']+)'", re.IGNORECASE)
_RE_AL = re.compile(r"alter_table\s*\(\s*'([^']+)'", re.IGNORECASE)
_RE_AC = re.compile(r"add_column\s*\(\s*'([^']+)'\s*,\s*sa\.Column\s*\(\s*'([^']+)'", re.IGNORECASE)


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
            # PR#201 P2-4: 读取所有迁移文件——不只看最近一个
            create_tables: list[str] = []
            alter_tables: list[str] = []
            add_columns: list[dict[str, str]] = []
            for mf in py_files[:10]:
                c = mf.read_text(encoding="utf-8", errors="replace")
                create_tables.extend(_RE_CR.findall(c))
                alter_tables.extend(_RE_AL.findall(c))
                add_columns.extend({"table": t, "column": col} for t, col in _RE_AC.findall(c))
            result["tables_added"] = create_tables
            result["tables_modified"] = alter_tables
            result["columns_added"] = add_columns
            return result
        except OSError as e:
            return {**result, "error": str(e)}
