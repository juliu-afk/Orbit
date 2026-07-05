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
