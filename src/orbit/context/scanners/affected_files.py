"""受影响的文件扫描器——git diff → 分类文件列表.

纯 git 命令——不用 LLM。非 git 项目返回空结果。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from orbit.context.scanners.base import BaseScanner


class AffectedFilesScanner(BaseScanner):
    """git diff → 按模块分类的文件变更列表。

    输出: {
        "changed": ["src/orbit/agents/react_agent.py", ...],
        "added": [...],
        "deleted": [...],
        "by_module": {"agents": [...], "scheduler": [...], ...},
        "total": 5
    }
    """

    name = "affected_files"

    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            root = Path(project_path)
            result = {"changed": [], "added": [], "deleted": [], "by_module": {}, "total": 0}

            # git diff --name-only 获取变更文件
            changed = self._git_diff(root, "--diff-filter=M")
            added = self._git_diff(root, "--diff-filter=A")
            deleted = self._git_diff(root, "--diff-filter=D")

            result["changed"] = changed
            result["added"] = added
            result["deleted"] = deleted

            all_files = changed + added + deleted
            result["total"] = len(all_files)

            # 按模块分组
            by_module: dict[str, list[str]] = {}
            for f in all_files:
                module = f.split("/")[0] if "/" in f else "root"
                by_module.setdefault(module, []).append(f)
            result["by_module"] = by_module

            return result
        except Exception as e:
            return {"error": str(e), "changed": [], "added": [], "deleted": [], "by_module": {}, "total": 0}

    @staticmethod
    def _git_diff(root: Path, flag: str) -> list[str]:
        """运行 git diff --name-only。非 git 项目/异常返回空列表。"""
        try:
            r = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", flag, "HEAD~1"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                return []
            return [f.strip() for f in r.stdout.splitlines() if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []
