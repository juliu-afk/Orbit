"""storage——.orbit/ 文件 I/O 辅助函数单元测试.

Focus: 纯路径逻辑. 使用 tmp_path 最小化 I/O.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from orbit.brief.storage import (
    ORBIT_DIR,
    BRIEF_FILE,
    CONTEXT_FILE,
    _ensure_orbit_dir,
    collect_context_md_hierarchy,
    read_context_md,
)


class TestConstants:
    def test_orbit_dir(self):
        assert ORBIT_DIR == ".orbit"

    def test_brief_file(self):
        assert BRIEF_FILE == "brief.md"

    def test_context_file(self):
        assert CONTEXT_FILE == "context.md"


class TestEnsureOrbitDir:
    def test_creates_directory(self, tmp_path):
        """_ensure_orbit_dir 创建 .orbit 目录并返回绝对路径."""
        project = str(tmp_path)
        result = _ensure_orbit_dir(project)
        expected = os.path.join(project, ORBIT_DIR)
        assert result == expected
        assert os.path.isdir(expected)

    def test_idempotent(self, tmp_path):
        """已存在时不会重复创建."""
        project = str(tmp_path)
        os.makedirs(os.path.join(project, ORBIT_DIR))
        result = _ensure_orbit_dir(project)
        assert os.path.isdir(result)


class TestReadContextMd:
    def test_file_not_found_returns_none(self, tmp_path):
        """context.md 不存在 → None."""
        result = read_context_md(str(tmp_path))
        assert result is None

    def test_reads_content(self, tmp_path):
        """读取 .orbit/context.md 内容."""
        orbit_dir = os.path.join(str(tmp_path), ORBIT_DIR)
        os.makedirs(orbit_dir)
        ctx_path = os.path.join(orbit_dir, CONTEXT_FILE)
        with open(ctx_path, "w", encoding="utf-8") as f:
            f.write("test context content")
        result = read_context_md(str(tmp_path))
        assert result == "test context content"


class TestCollectContextMdHierarchy:
    """路径向上遍历——按层级收集 context.md."""

    def test_single_level(self, tmp_path):
        """项目根有 context.md → 返回单条."""
        root = str(tmp_path)
        orbit_dir = os.path.join(root, ORBIT_DIR)
        os.makedirs(orbit_dir)
        with open(os.path.join(orbit_dir, CONTEXT_FILE), "w", encoding="utf-8") as f:
            f.write("root context")
        target = os.path.join(root, "some_file.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# test")
        results = collect_context_md_hierarchy(target, root)
        assert len(results) == 1
        assert results[0][0] == root
        assert results[0][1] == "root context"

    def test_multi_level(self, tmp_path):
        """多层级收集——从项目根到目标目录均有 context.md."""
        root = str(tmp_path)
        # root .orbit/context.md
        os.makedirs(os.path.join(root, ORBIT_DIR))
        with open(os.path.join(root, ORBIT_DIR, CONTEXT_FILE), "w", encoding="utf-8") as f:
            f.write("root context")
        # subdir .orbit/context.md
        subdir = os.path.join(root, "subdir")
        os.makedirs(os.path.join(subdir, ORBIT_DIR))
        with open(os.path.join(subdir, ORBIT_DIR, CONTEXT_FILE), "w", encoding="utf-8") as f:
            f.write("subdir context")
        target = os.path.join(subdir, "target.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# test")
        results = collect_context_md_hierarchy(target, root)
        assert len(results) == 2
        # 项目根优先（反转后 root 在前）
        assert results[0][0] == root
        assert "root context" in results[0][1]
        assert results[1][0] == subdir
        assert "subdir context" in results[1][1]

    def test_no_context_md(self, tmp_path):
        """目录中没有 context.md → 返回空列表."""
        root = str(tmp_path)
        target = os.path.join(root, "file.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# test")
        results = collect_context_md_hierarchy(target, root)
        assert results == []

    def test_partial_coverage(self, tmp_path):
        """部分层级有 context.md — 只返回有文件的."""
        root = str(tmp_path)
        # 只有子目录有，项目根没有
        subdir = os.path.join(root, "subdir")
        os.makedirs(os.path.join(subdir, ORBIT_DIR))
        with open(os.path.join(subdir, ORBIT_DIR, CONTEXT_FILE), "w", encoding="utf-8") as f:
            f.write("subdir only")
        target = os.path.join(subdir, "target.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# test")
        results = collect_context_md_hierarchy(target, root)
        assert len(results) == 1
        assert results[0][0] == subdir

    def test_stops_at_project_root(self, tmp_path):
        """不走出项目根目录."""
        root = str(tmp_path)
        # 项目根外也有 .orbit/context.md（不应收集）
        parent = os.path.dirname(root)
        os.makedirs(os.path.join(parent, ORBIT_DIR), exist_ok=True)
        with open(os.path.join(parent, ORBIT_DIR, CONTEXT_FILE), "w", encoding="utf-8") as f:
            f.write("outside project")
        target = os.path.join(root, "file.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# test")
        results = collect_context_md_hierarchy(target, root)
        assert all(r[0] == root or r[0].startswith(root) for r in results)
