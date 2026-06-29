"""文件服务——文件列表、读取、diff 生成。

WHY subprocess git 而非 GitPython 做 diff：
GitPython 在大仓库性能差，git diff --unified 子进程更稳定。
"""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class FileInfo(BaseModel):
    path: str  # relative to workspace root
    size: int
    status: FileStatus
    review_status: str | None = None  # approved | rejected | pending | null（未审查）


class FileService:
    """文件服务——workspace 文件操作。

    不依赖 async ORM——直接操作文件系统和 git 子进程。
    """

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()

    def _safe_path(self, relative: str) -> Path:
        """安全检查：确保路径在 workspace 内，防路径遍历攻击。"""
        resolved = (self.workspace / relative).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise ValueError(f"路径遍历拒绝: {relative}")
        return resolved

    # ── 文件列表 ──

    async def list_files(self, task_id: str | None = None) -> list[FileInfo]:
        """列出 workspace 中所有文本文件。

        排除：__pycache__、node_modules、.git、.venv、data/ 等。
        task_id 为 None 时列出全项目，非 None 时仅列出该 task 涉及的文件。
        """
        EXCLUDE_DIRS = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            "data", ".orbit", ".claude", "dist", "build", ".mypy_cache",
            ".ruff_cache", ".pytest_cache",
        }
        EXCLUDE_EXT = {".pyc", ".pyo", ".exe", ".dll", ".so", ".o", ".db"}
        TEXT_EXT = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".scss",
            ".html", ".md", ".json", ".yaml", ".yml", ".toml", ".sql",
            ".txt", ".cfg", ".ini", ".env", ".sh", ".dockerfile", ".svg",
        }

        files = []
        for root, dirs, filenames in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in EXCLUDE_EXT:
                    continue
                if ext not in TEXT_EXT and f not in TEXT_EXT:
                    continue
                full = Path(root) / f
                rel = str(full.relative_to(self.workspace)).replace("\\", "/")
                files.append(FileInfo(
                    path=rel,
                    size=full.stat().st_size,
                    status=FileStatus.UNCHANGED,
                ))
        return sorted(files, key=lambda x: x.path)

    # ── 文件读取 ──

    async def read_file(self, path: str) -> str:
        """读取文件内容（UTF-8）。"""
        target = self._safe_path(path)
        return target.read_text(encoding="utf-8")

    def detect_language(self, path: str) -> str:
        """从文件扩展名推断 Monaco 语言 ID。"""
        ext = os.path.splitext(path)[1].lower()
        MAP = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript", ".vue": "html",
            ".css": "css", ".scss": "scss", ".html": "html",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".toml": "toml", ".sql": "sql", ".md": "markdown",
            ".sh": "shell", ".dockerfile": "dockerfile",
            ".svg": "xml", ".xml": "xml",
        }
        return MAP.get(ext, "plaintext")

    # ── Diff 生成 ──

    async def diff(
        self, path: str, rev_a: str = "HEAD", rev_b: str | None = None
    ) -> dict:
        """生成文件的 unified diff。

        rev_a: 旧版本（默认 HEAD）
        rev_b: 新版本（默认工作区），为 None 时读文件系统当前内容。
        """
        target = self._safe_path(path)
        # WHY subprocess git diff：GitPython 在大仓库性能差
        cmd = ["git", "-C", str(self.workspace), "diff", "--unified=3"]
        if rev_b:
            cmd.extend([rev_a, rev_b, "--", str(target)])
        else:
            cmd.extend([rev_a, "--", str(target)])
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return {
                "diff_text": stdout.decode("utf-8", errors="replace"),
                "language": self.detect_language(path),
            }
        return {
            "diff_text": "",
            "language": self.detect_language(path),
            "error": stderr.decode("utf-8", errors="replace") if stderr else "",
        }

    async def diff_checkpoint(
        self, task_id: str, before_rev: str, after_rev: str
    ) -> dict[str, dict]:
        """获取 task 前后所有变更文件的 diff。

        before_rev/after_rev 来自检查点的 git rev。
        """
        cmd = [
            "git", "-C", str(self.workspace), "diff", "--name-only",
            before_rev, after_rev,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        changed_files = stdout.decode("utf-8").strip().split("\n") if stdout else []

        diffs = {}
        for f in changed_files:
            if not f:
                continue
            diffs[f] = await self.diff(f, before_rev, after_rev)
        return diffs

    # ── 写入（Phase 2 轻量编辑器预留） ──

    async def write_file(self, path: str, content: str) -> None:
        """写入文件内容（Phase 2 启用）。"""
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
