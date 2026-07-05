"""测试覆盖率缺口扫描器——coverage.json → 变更文件覆盖状态.

Phase B 实现——当前返回骨架结构。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orbit.context.scanners.base import BaseScanner


class TestCoverageScanner(BaseScanner):
    """coverage.json → 变更文件的覆盖率缺口。

    输出: {
        "gaps": [{"file": "...", "coverage_pct": 45.0, "missing_lines": [10,20,30]}, ...],
        "overall_coverage": 78.5,
        "files_under_threshold": ["...", ...]
    }
    """

    name = "test_coverage"

    def scan(self, project_path: str, affected_files: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "gaps": [],
            "overall_coverage": 0.0,
            "files_under_threshold": [],
        }

        root = Path(project_path)
        coverage_path = root / "coverage.json"
        if not coverage_path.exists():
            return {**result, "note": "coverage.json not found"}

        try:
            data = json.loads(coverage_path.read_text(encoding="utf-8"))
            files_data = data.get("files", {})

            # 计算整体覆盖率
            summary = data.get("totals", {})
            result["overall_coverage"] = summary.get("percent_covered", 0.0)

            # 找出变更文件中低于 80% 的文件
            target_files = set(affected_files or [])
            for file_path, file_info in files_data.items():
                pct = file_info.get("summary", {}).get("percent_covered", 100.0)
                if pct < 80.0 and (not target_files or file_path in target_files):
                    missing = file_info.get("missing_lines", [])
                    result["gaps"].append({
                        "file": file_path,
                        "coverage_pct": pct,
                        "missing_lines": missing[:20],  # 最多 20 行——防止过大
                    })
                    result["files_under_threshold"].append(file_path)

            return result
        except (json.JSONDecodeError, OSError, KeyError) as e:
            return {**result, "error": str(e)}
