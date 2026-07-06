"""文件服务——文件列表、读取、diff 生成。"""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

MAX_READ_SIZE = 1_000_000  # 1MB 上限，超限拒绝读取 (P0-6)
# 无扩展名但应显示的文件 (P1-6)
NAMELESS_WHITELIST = {"Makefile", "Dockerfile", "LICENSE", ".gitignore", ".env", ".dockerignore"}


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class FileInfo(BaseModel):
    path: str
    size: int
    status: FileStatus
    review_status: str | None = None


class FileService:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()

    def _safe_path(self, relative: str) -> Path:
        resolved = (self.workspace / relative).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise ValueError(f"Path traversal denied: {relative}")
        return resolved

    # P0-5: 提取同步逻辑，通过 asyncio.to_thread 避免阻塞事件循环
    def _list_files_sync(self, root_override: str | None = None) -> list[FileInfo]:
        walk_root = root_override if root_override else self.workspace
        EXCLUDE_DIRS = {
            "__pycache__",
            "node_modules",
            ".git",
            ".venv",
            "venv",
            "data",
            ".orbit",
            ".claude",
            "dist",
            "build",
            ".mypy_cache",
            ".ruff_cache",
            ".pytest_cache",
        }
        EXCLUDE_EXT = {".pyc", ".pyo", ".exe", ".dll", ".so", ".o", ".db"}
        TEXT_EXT = {
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".vue",
            ".css",
            ".scss",
            ".html",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".sql",
            ".txt",
            ".cfg",
            ".ini",
            ".env",
            ".sh",
            ".svg",
        }
        files = []
        for root, dirs, filenames in os.walk(walk_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in EXCLUDE_EXT:
                    continue
                if ext not in TEXT_EXT and f not in NAMELESS_WHITELIST:
                    continue
                full = Path(root) / f
                base = Path(walk_root) if root_override else self.workspace
                rel = str(full.relative_to(base)).replace("\\", "/")
                files.append(
                    FileInfo(path=rel, size=full.stat().st_size, status=FileStatus.UNCHANGED)
                )
        return sorted(files, key=lambda x: x.path)

    async def list_files(self, directory: str | None = None) -> list[FileInfo]:
        # WHY dir override: 用户打开项目后文件树应展示项目目录，非 exe 所在目录
        if directory:
            import functools
            return await asyncio.to_thread(functools.partial(self._list_files_sync, root_override=directory))
        return await asyncio.to_thread(self._list_files_sync)

    async def read_file(self, path: str) -> str:
        target = self._safe_path(path)
        if target.stat().st_size > MAX_READ_SIZE:
            raise ValueError(f"File too large: {target.stat().st_size} > {MAX_READ_SIZE}")
        return target.read_text(encoding="utf-8")

    def detect_language(self, path: str) -> str:
        M = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".vue": "html",
            ".css": "css",
            ".scss": "scss",
            ".html": "html",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".sql": "sql",
            ".md": "markdown",
            ".sh": "shell",
            ".svg": "xml",
            ".xml": "xml",
        }
        return M.get(os.path.splitext(path)[1].lower(), "plaintext")

    async def diff(self, path: str, rev_a: str = "HEAD", rev_b: str | None = None) -> dict:
        target = self._safe_path(path)
        cmd = ["git", "-C", str(self.workspace), "diff", "--unified=3"]
        if rev_b:
            cmd.extend([rev_a, rev_b, "--", str(target)])
        else:
            cmd.extend([rev_a, "--", str(target)])
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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

    async def write_file(self, path: str, content: str) -> None:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
