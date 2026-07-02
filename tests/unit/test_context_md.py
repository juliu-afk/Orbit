"""CONTEXT.md 层级 单元测试。"""

import os
import tempfile
from pathlib import Path

from orbit.brief.storage import (
    collect_context_md_hierarchy,
    read_context_md,
    write_context_md,
)


class TestContextMdIO:
    def test_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_context_md(tmpdir, "test content")
            assert os.path.isfile(path)
            content = read_context_md(tmpdir)
            assert content == "test content"

    def test_read_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            content = read_context_md(tmpdir)
            assert content is None

    def test_write_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            write_context_md(tmpdir, "v1")
            write_context_md(tmpdir, "v2")
            assert read_context_md(tmpdir) == "v2"


class TestCollectHierarchy:
    def test_single_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # project root
            orbit_dir = os.path.join(tmpdir, ".orbit")
            os.makedirs(orbit_dir)
            Path(orbit_dir, "context.md").write_text("root context", encoding="utf-8")

            # target file in subdirectory
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)
            target = os.path.join(src_dir, "main.py")
            Path(target).write_text("print('hello')")

            results = collect_context_md_hierarchy(target, tmpdir)
            assert len(results) == 1
            assert results[0][1] == "root context"

    def test_multi_level_priority(self) -> None:
        """child context.md later in list = higher priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # project root
            Path(tmpdir, ".orbit").mkdir()
            Path(tmpdir, ".orbit/context.md").write_text("root", encoding="utf-8")

            # src dir
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/.orbit").mkdir()
            Path(tmpdir, "src/.orbit/context.md").write_text("src", encoding="utf-8")

            # src/api dir - where target lives
            Path(tmpdir, "src/api").mkdir(parents=True)
            Path(tmpdir, "src/api/.orbit").mkdir()
            Path(tmpdir, "src/api/.orbit/context.md").write_text("api", encoding="utf-8")

            target = os.path.join(tmpdir, "src", "api", "routes.py")
            Path(target).write_text("pass")

            results = collect_context_md_hierarchy(target, tmpdir)
            assert len(results) == 3
            # order: root -> src -> src/api
            assert results[0][1] == "root"
            assert results[1][1] == "src"
            assert results[2][1] == "api"

    def test_no_context_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "src").mkdir()
            target = os.path.join(tmpdir, "src", "main.py")
            Path(target).write_text("x")

            results = collect_context_md_hierarchy(target, tmpdir)
            assert results == []

    def test_target_outside_project(self) -> None:
        """target outside project root -> empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".orbit").mkdir()
            Path(tmpdir, ".orbit/context.md").write_text("x", encoding="utf-8")

            other_dir = tempfile.mkdtemp()
            target = os.path.join(other_dir, "outside.py")
            Path(target).write_text("x")

            results = collect_context_md_hierarchy(target, tmpdir)
            assert results == []
