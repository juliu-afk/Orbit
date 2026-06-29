"""文件服务——文件列表、读取、diff 生成。"""
from __future__ import annotations
import asyncio, os
from enum import Enum
from pathlib import Path
from pydantic import BaseModel

class FileStatus(str, Enum):
    ADDED="added"; MODIFIED="modified"; DELETED="deleted"; UNCHANGED="unchanged"

class FileInfo(BaseModel):
    path: str; size: int; status: FileStatus; review_status: str | None = None

class FileService:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()

    def _safe_path(self, relative: str) -> Path:
        resolved = (self.workspace / relative).resolve()
        if not str(resolved).startswith(str(self.workspace)):
            raise ValueError(f"Path traversal denied: {relative}")
        return resolved

    async def list_files(self, task_id: str | None = None) -> list[FileInfo]:
        EXCLUDE_DIRS = {"__pycache__","node_modules",".git",".venv","venv","data",".orbit",".claude","dist","build",".mypy_cache",".ruff_cache",".pytest_cache"}
        EXCLUDE_EXT = {".pyc",".pyo",".exe",".dll",".so",".o",".db"}
        TEXT_EXT = {".py",".ts",".tsx",".js",".jsx",".vue",".css",".scss",".html",".md",".json",".yaml",".yml",".toml",".sql",".txt",".cfg",".ini",".env",".sh",".svg"}
        files = []
        for root, dirs, filenames in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                if ext in EXCLUDE_EXT: continue
                if ext not in TEXT_EXT and f not in TEXT_EXT: continue
                full = Path(root) / f
                rel = str(full.relative_to(self.workspace)).replace("\\", "/")
                files.append(FileInfo(path=rel, size=full.stat().st_size, status=FileStatus.UNCHANGED))
        return sorted(files, key=lambda x: x.path)

    async def read_file(self, path: str) -> str:
        return self._safe_path(path).read_text(encoding="utf-8")

    def detect_language(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        M = {".py":"python",".ts":"typescript",".tsx":"typescript",".js":"javascript",".jsx":"javascript",".vue":"html",".css":"css",".scss":"scss",".html":"html",".json":"json",".yaml":"yaml",".yml":"yaml",".toml":"toml",".sql":"sql",".md":"markdown",".sh":"shell",".svg":"xml",".xml":"xml"}
        return M.get(ext, "plaintext")

    async def diff(self, path: str, rev_a: str = "HEAD", rev_b: str | None = None) -> dict:
        target = self._safe_path(path)
        cmd = ["git","-C",str(self.workspace),"diff","--unified=3"]
        if rev_b: cmd.extend([rev_a, rev_b, "--", str(target)])
        else: cmd.extend([rev_a, "--", str(target)])
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return {"diff_text": stdout.decode("utf-8", errors="replace"), "language": self.detect_language(path)}
        return {"diff_text": "", "language": self.detect_language(path), "error": stderr.decode("utf-8", errors="replace") if stderr else ""}

    async def write_file(self, path: str, content: str) -> None:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
