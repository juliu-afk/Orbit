"""ConfigStore——Git 后端配置管理（Inkeep 借鉴 #5）。

WHY Git 后端: branch/merge/diff/log/rollback 全部免费获得。
每次保存 = 一次 git commit。零额外存储设计。

配置目录: ~/.orbit/config/  (Git 仓库)
  ├── model_routing.yaml
  ├── artifact_tiers.yaml
  ├── prompts/
  │   ├── architect.yaml
  │   └── ...
  ├── hallucination.yaml
  └── trace.yaml
"""

from __future__ import annotations

import asyncio.subprocess
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger("orbit.config_store")

CONFIG_HOME = Path.home() / ".orbit" / "config"
CONFIG_DEFAULTS = Path(__file__).resolve().parent / "config"  # 默认 YAML 模板


class ConfigSection(StrEnum):
    MODEL_ROUTING = "model_routing"
    ARTIFACT_TIERS = "artifact_tiers"
    PROMPTS = "prompts"
    HALLUCINATION = "hallucination"
    TRACE = "trace"


@dataclass
class GitCommit:
    """Git commit 元数据。"""
    hash: str           # short hash (7 char)
    full_hash: str      # full 40-char hash
    message: str
    author: str
    timestamp: str      # ISO format
    file: str = ""      # 变更文件路径


@dataclass
class GitBranch:
    name: str
    is_current: bool
    last_commit: GitCommit | None = None


@dataclass
class MergeResult:
    success: bool
    conflict_files: list[str] = field(default_factory=list)
    message: str = ""


class ConfigError(Exception):
    """配置操作错误。"""


class ConfigStore:
    """配置存储——YAML 文件 + Git 仓库。

    用法:
        store = ConfigStore()
        store.init()                          # 首次初始化
        data = store.read(ConfigSection.MODEL_ROUTING)
        commit = store.write(ConfigSection.MODEL_ROUTING, data, author="admin")
        history = store.history(ConfigSection.MODEL_ROUTING)
        diff = store.diff("abc123", "def456", "model_routing.yaml")
        store.rollback(ConfigSection.MODEL_ROUTING, "abc123", author="admin")
    """

    def __init__(self, repo_path: Path | None = None) -> None:
        self.repo_path = repo_path or CONFIG_HOME

    # ── 初始化 ────────────────────────────────────────────

    def init(self) -> bool:
        """幂等初始化——创建目录 + git init + 首次 commit 默认配置。"""
        self.repo_path.mkdir(parents=True, exist_ok=True)

        git_dir = self.repo_path / ".git"
        if git_dir.exists():
            return False  # 已初始化

        # 复制默认配置模板
        if CONFIG_DEFAULTS.exists():
            for f in CONFIG_DEFAULTS.iterdir():
                dest = self.repo_path / f.name
                if not dest.exists():
                    if f.is_dir():
                        shutil.copytree(f, dest)
                    else:
                        shutil.copy2(f, dest)

        # git init + 首次 commit
        self._run_git_sync("init")
        self._run_git_sync("add", "-A")
        self._run_git_sync("commit", "-m", "init: default config")
        logger.info("config_store_initialized", path=str(self.repo_path))
        return True

    # ── 读写 ──────────────────────────────────────────────

    def read(self, section: ConfigSection | str) -> dict:
        """读取配置 section，返回 dict。"""
        filepath = self._section_path(section)
        if not filepath.exists():
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def write(self, section: ConfigSection | str, data: dict, author: str = "ui") -> str:
        """写配置 section → YAML 文件 → git commit。返回 commit hash。"""
        filepath = self._section_path(section)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 写 YAML
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

        # git add + commit
        rel_path = filepath.relative_to(self.repo_path)
        self._run_git_sync("add", str(rel_path))
        self._run_git_sync(
            "commit", "-m",
            f"config: update {section.value if isinstance(section, ConfigSection) else section}",
            "--author", f"{author} <{author}@orbit.local>",
        )
        return self._head_hash()

    # ── 版本历史 ──────────────────────────────────────────

    def history(self, section: ConfigSection | str | None = None, limit: int = 20) -> list[GitCommit]:
        """Git log——指定 section 则只显示该文件的历史。"""
        filepath = self._section_path(section) if section else None
        args = ["log", f"--max-count={limit}", "--format=%H|%h|%s|%an|%aI"]
        if filepath and filepath.exists():
            args.extend(["--", str(filepath.relative_to(self.repo_path))])
        output = self._run_git_sync(*args)
        return self._parse_commits(output)

    def diff(self, from_hash: str, to_hash: str, section: ConfigSection | str) -> str:
        """两个 commit 之间某个文件的 unified diff。"""
        filepath = self._section_path(section)
        rel = str(filepath.relative_to(self.repo_path))
        return self._run_git_sync("diff", from_hash, to_hash, "--", rel)

    # ── 回滚 ──────────────────────────────────────────────

    def rollback(self, section: ConfigSection | str, commit_hash: str, author: str = "ui") -> str:
        """回滚到指定 commit——checkout 该版本的文件 + 新 commit。"""
        filepath = self._section_path(section)
        rel = str(filepath.relative_to(self.repo_path))
        self._run_git_sync("checkout", commit_hash, "--", rel)
        self._run_git_sync("add", rel)
        self._run_git_sync(
            "commit", "-m",
            f"config: rollback {section.value if isinstance(section, ConfigSection) else section} to {commit_hash[:7]}",
            "--author", f"{author} <{author}@orbit.local>",
        )
        return self._head_hash()

    # ── 分支操作 ──────────────────────────────────────────

    def branches(self) -> list[GitBranch]:
        """列出所有分支。"""
        output = self._run_git_sync("branch", "--list")
        result: list[GitBranch] = []
        current_branch = self._current_branch_name()
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            is_current = line.startswith("*")
            name = line.lstrip("*").strip()
            result.append(GitBranch(name=name, is_current=is_current))
        return result

    def create_branch(self, name: str) -> str:
        """创建新分支。"""
        self._run_git_sync("checkout", "-b", name)
        return name

    def switch_branch(self, name: str) -> str:
        """切换分支。"""
        self._run_git_sync("checkout", name)
        return name

    def merge(self, from_branch: str, author: str = "ui") -> MergeResult:
        """合并分支——冲突时返回冲突文件列表。"""
        current = self._current_branch_name()
        try:
            output = self._run_git_sync("merge", from_branch, "--no-edit")
            return MergeResult(success=True, message=output[:200])
        except ConfigError as e:
            msg = str(e)
            if "CONFLICT" in msg or "conflict" in msg.lower():
                conflict_files = self._conflict_files()
                return MergeResult(
                    success=False,
                    conflict_files=conflict_files,
                    message=f"合并冲突：{len(conflict_files)} 个文件需要手动解决",
                )
            raise

    def conflict_content(self, section: ConfigSection | str) -> str:
        """读取冲突文件的原始内容（含 <<<<<<< 标记）。"""
        filepath = self._section_path(section)
        return filepath.read_text(encoding="utf-8")

    def resolve_conflict(self, section: ConfigSection | str, resolved: str, author: str = "ui") -> str:
        """手动解决冲突——写文件 + git add + git commit。"""
        filepath = self._section_path(section)
        filepath.write_text(resolved, encoding="utf-8")
        rel = str(filepath.relative_to(self.repo_path))
        self._run_git_sync("add", rel)
        self._run_git_sync(
            "commit", "-m",
            f"config: resolve conflict {section.value if isinstance(section, ConfigSection) else section}",
            "--author", f"{author} <{author}@orbit.local>",
        )
        return self._head_hash()

    # ── 内部 ──────────────────────────────────────────────

    def _section_path(self, section: ConfigSection | str) -> Path:
        section_name = section.value if isinstance(section, ConfigSection) else section
        return self.repo_path / f"{section_name}.yaml"

    def _run_git_sync(self, *args: str) -> str:
        """同步执行 git 命令——subprocess.run。"""
        try:
            import subprocess
            import sys

            # P2-3: Windows 上隐藏控制台窗口（CREATE_NO_WINDOW = 0x08000000）
            kwargs: dict = dict(
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

            result = subprocess.run(["git", *args], **kwargs)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # 空提交（nothing to commit）不是错误
                if "nothing to commit" in stderr or "nothing added to commit" in stderr:
                    return ""
                raise ConfigError(f"git {' '.join(args)}: {stderr}")
            return result.stdout
        except subprocess.TimeoutExpired:
            raise ConfigError(f"git {' '.join(args)} timed out")

    def _head_hash(self) -> str:
        """获取 HEAD 完整 hash。"""
        return self._run_git_sync("rev-parse", "HEAD").strip()

    def _current_branch_name(self) -> str:
        return self._run_git_sync("rev-parse", "--abbrev-ref", "HEAD").strip()

    def _conflict_files(self) -> list[str]:
        """列出冲突文件。"""
        output = self._run_git_sync("diff", "--name-only", "--diff-filter=U")
        return [f.strip() for f in output.strip().split("\n") if f.strip()]

    @staticmethod
    def _parse_commits(output: str) -> list[GitCommit]:
        """解析 git log 格式: %H|%h|%s|%an|%aI。"""
        commits: list[GitCommit] = []
        for line in output.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append(GitCommit(
                    full_hash=parts[0],
                    hash=parts[1],
                    message=parts[2],
                    author=parts[3],
                    timestamp=parts[4],
                ))
        return commits
