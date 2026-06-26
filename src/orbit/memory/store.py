"""文件记忆存储 (Phase 2 AC9).

CRUD 操作 MEMORY.md / checkpoint.md / progress.md / notes.md.
YAML frontmatter + markdown body 格式。
双向同步 (file ↔ memory reconcile).

WHY 文件而非 SQLite: Markdown 人可读，符合 MiMo Code 设计。
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import structlog

from orbit.memory.models import (
    MemoryConfig,
    MemoryFile,
    MemoryFileType,
    MemorySearchQuery,
    MemorySearchResult,
)

logger = structlog.get_logger("orbit.memory")

# YAML frontmatter 正则——提取两个 `---` 之间的内容
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class MemoryStore:
    """文件记忆存储——CRUD + 搜索.

    Usage:
        store = MemoryStore(project_path="/project/root")
        mem = store.read_file(MemoryFileType.EPISODIC)
        store.append_to_file(MemoryFileType.EPISODIC, "## New Section\\n...")
    """

    def __init__(self, project_path: str = "") -> None:
        self._config = MemoryConfig(project_root=project_path)
        self._resolve_memory_dir()

    # ── 读 ─────────────────────────────────────────────

    def read_file(self, file_type: MemoryFileType) -> MemoryFile:
        """读取一个记忆文件——解析 frontmatter + body."""
        path = self._path_for(file_type)
        mem = MemoryFile(path=str(path), file_type=file_type)

        if not path.exists():
            return mem

        content = path.read_text(encoding="utf-8", errors="replace")
        mem.checksum_sha256 = _sha256(content)
        mem.updated_at = path.stat().st_mtime

        # 解析 frontmatter
        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            mem.body = content[fm_match.end() :]
            mem.frontmatter = _parse_yaml_frontmatter(fm_match.group(1))
        else:
            mem.body = content

        return mem

    def read_for_agent(self, agent_name: str) -> MemoryFile:
        """读取与当前 Agent 相关的记忆——过滤 MEMORY.md 中对应的 Section."""
        mem = self.read_file(MemoryFileType.EPISODIC)
        # 过滤 body 中与 agent_name 相关的 Section
        if agent_name and mem.body:
            sections = re.split(r"\n## ", mem.body)
            relevant = [
                s
                for s in sections
                if agent_name.lower() in s.lower() or "通用" in s or "General" in s
            ]
            if relevant:
                mem.body = "## ".join(relevant)
        return mem

    # ── 写 ─────────────────────────────────────────────

    def write_file(
        self, file_type: MemoryFileType, body: str, frontmatter: dict | None = None
    ) -> None:
        """写入整个记忆文件——带 frontmatter."""
        path = self._path_for(file_type)
        path.parent.mkdir(parents=True, exist_ok=True)

        fm = dict(frontmatter or {})
        fm.setdefault("updated", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        content = _build_frontmatter(fm) + "\n" + body
        path.write_text(content, encoding="utf-8")
        logger.info("memory_file_written", path=str(path), size=len(content))

    def append_to_file(self, file_type: MemoryFileType, entry: str) -> None:
        """追加条目到记忆文件——保留已有内容."""
        existing = self.read_file(file_type)
        new_body = existing.body.rstrip() + "\n\n" + entry.strip() + "\n"

        # 检查大小限制
        if len(new_body.encode("utf-8")) > self._config.max_memory_file_size:
            # 截断旧内容，保留最近的 70%
            split_point = int(len(existing.body) * 0.3)
            truncated = existing.body[split_point:]
            new_body = (
                f"[旧记忆已归档——超出 {self._config.max_memory_file_size // 1000}KB 限制]\n\n"
                + truncated.rstrip()
                + "\n\n"
                + entry.strip()
                + "\n"
            )
            logger.warning("memory_file_truncated", path=str(self._path_for(file_type)))

        self.write_file(file_type, new_body, existing.frontmatter)

    # ── 搜索 ───────────────────────────────────────────

    def search(self, query: MemorySearchQuery) -> list[MemorySearchResult]:
        """在记忆文件中搜索——简单子字符串匹配.

        Phase 2 基础实现，Phase 3 升级为 FTS5+BM25。
        """
        results: list[MemorySearchResult] = []
        pattern = query.query.lower()

        file_types = [query.file_type] if query.file_type else list(MemoryFileType)
        for ft in file_types:
            mem = self.read_file(ft)
            if not mem.body:
                continue
            for i, line in enumerate(mem.body.splitlines()):
                if pattern in line.lower():
                    # 简单评分：匹配长度 / 行长度
                    score = len(pattern) / max(len(line), 1)
                    results.append(
                        MemorySearchResult(
                            path=mem.path,
                            score=score,
                            snippet=line.strip()[:200],
                            line_number=i + 1,
                        )
                    )

        # 按评分排序
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: query.max_results]

    # ── 同步 ───────────────────────────────────────────

    def reconcile(self, file_type: MemoryFileType, in_memory_version: MemoryFile) -> bool:
        """双向同步——检测冲突并合并.

        Returns:
            True 如果内存版本与文件版本一致（无需修复）
        """
        disk_version = self.read_file(file_type)
        if disk_version.checksum_sha256 == in_memory_version.checksum_sha256:
            return True  # 一致

        # 冲突：保留磁盘版本，返回 False 让调用方决定
        logger.warning(
            "memory_conflict",
            file_type=file_type.value,
            disk_checksum=disk_version.checksum_sha256[:8],
            mem_checksum=in_memory_version.checksum_sha256[:8],
        )
        return False

    # ── 内部 ───────────────────────────────────────────

    def _path_for(self, file_type: MemoryFileType) -> Path:
        return self._config.memory_dir_path / file_type.value

    @property
    def _config(self) -> MemoryConfig:
        return self.__dict__["_config"]

    @_config.setter
    def _config(self, value: MemoryConfig) -> None:
        self.__dict__["_config"] = value

    def _resolve_memory_dir(self) -> None:
        """解析记忆目录路径."""
        base = Path(self._config.project_root) if self._config.project_root else Path.cwd()
        self._config.memory_dir_path = base / self._config.memory_dir


# ── 辅助 ──────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_yaml_frontmatter(fm_text: str) -> dict:
    """极简 YAML 解析——仅支持 key: value 格式."""
    result: dict = {}
    for line in fm_text.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _build_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)
