"""git diff → 分类文件列表. PR#201 P1-2: merge-base替代HEAD~1."""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any
from orbit.context.scanners.base import BaseScanner

class AffectedFilesScanner(BaseScanner):
    name = "affected_files"
    def scan(self, project_path: str, base_branch: str = "master", **kwargs: Any) -> dict[str, Any]:
        try:
            root = Path(project_path)
            result = {"changed": [], "added": [], "deleted": [], "by_module": {}, "total": 0}
            changed = self._git_diff(root, "--diff-filter=M", base_branch)
            added = self._git_diff(root, "--diff-filter=A", base_branch)
            deleted = self._git_diff(root, "--diff-filter=D", base_branch)
            result["changed"] = changed
            result["added"] = added
            result["deleted"] = deleted
            all_files = changed + added + deleted
            result["total"] = len(all_files)
            by_module: dict[str, list[str]] = {}
            for f in all_files:
                module = f.split("/")[0] if "/" in f else "root"
                by_module.setdefault(module, []).append(f)
            result["by_module"] = by_module
            return result
        except Exception as e:
            return {"error": str(e), "changed": [], "added": [], "deleted": [], "by_module": {}, "total": 0}
    @staticmethod
    def _git_diff(root: Path, flag: str, base_branch: str = "master") -> list[str]:
        try:
            r = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", flag, f"origin/{base_branch}...HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                r = subprocess.run(
                    ["git", "-C", str(root), "diff", "--name-only", flag, "HEAD~1"],
                    capture_output=True, text=True, timeout=5,
                )
            if r.returncode != 0:
                return []
            return [f.strip() for f in r.stdout.splitlines() if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []
