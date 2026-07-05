"""数据库 schema 变更扫描器——Alembic migration → 表/列变更摘要.

Phase B 实现——当前返回骨架结构。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orbit.context.scanners.base import BaseScanner


class SchemaChangeScanner(BaseScanner):
    """Alembic migration 文件 → 表/列变更摘要。

    输出: {
        "tables_added": ["new_table", ...],
        "tables_modified": ["existing_table", ...],
        "columns_added": [{"table": "...", "column": "...", "type": "..."}, ...],
        "has_migration": true | false
    }
    """

    name = "schema_change"

    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tables_added": [],
            "tables_modified": [],
            "columns_added": [],
            "has_migration": False,
        }

        root = Path(project_path)
        # 常见 Alembic 迁移目录
        candidates = [
            root / "alembic" / "versions",
            root / "migrations",
            root / "backend" / "alembic" / "versions",
        ]

        migrations_dir = None
        for c in candidates:
            if c.exists() and c.is_dir():
                migrations_dir = c
                break

        if migrations_dir is None:
            return {**result, "note": "no migration directory found"}

        # 找最近修改的迁移文件
        try:
            py_files = sorted(
                migrations_dir.glob("*.py"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not py_files:
                return result

            result["has_migration"] = True
            latest = py_files[0]
            content = latest.read_text(encoding="utf-8", errors="replace")

            # 简单正则提取 create_table / alter_table 操作
            import re
            create_tables = re.findall(r"create_table\s*\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
            alter_tables = re.findall(r"alter_table\s*\(\s*['\"]([^'\"]+)['\"]", content, re.IGNORECASE)
            add_columns = re.findall(
                r"add_column\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*sa\.Column\s*\(\s*['\"]([^'\"]+)['\"]",
                content, re.IGNORECASE,
            )

            result["tables_added"] = create_tables
            result["tables_modified"] = alter_tables
            result["columns_added"] = [
                {"table": t, "column": c} for t, c in add_columns
            ]
            return result
        except OSError as e:
            return {**result, "error": str(e)}
