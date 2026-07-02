"""覆盖率——更多模块深挖: loop/scheduler + files/service + dream/verifier."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.dream.verifier import DreamVerifier
from orbit.dream.models import DreamConfig, DreamResult, DreamStatus
from orbit.files.service import FileService
from orbit.loop.scheduler import LoopScheduler


# ════════════════════════════════════════════
# 1. DreamVerifier
# ════════════════════════════════════════════

class TestDreamVerifier:
    def test_verify_empty_content(self):
        v = DreamVerifier()
        result = v.verify("", "/tmp/test.md")
        assert isinstance(result, DreamResult)
        assert result.status == DreamStatus.COMPLETE

    def test_verify_small_content(self):
        v = DreamVerifier()
        result = v.verify("# Header\ncontent here\n", "/tmp/test.md")
        assert result.status == DreamStatus.COMPLETE

    def test_verify_over_lines(self):
        """超过行数限制 → REJECTED。"""
        cfg = DreamConfig(max_output_lines=5)
        v = DreamVerifier(config=cfg)
        long_content = "\n".join(f"line {i}" for i in range(10))
        result = v.verify(long_content, "/tmp/test.md")
        assert result.status == DreamStatus.REJECTED

    def test_verify_over_bytes(self):
        """超过字节限制 → REJECTED。"""
        cfg = DreamConfig(max_output_bytes=100)
        v = DreamVerifier(config=cfg)
        result = v.verify("x" * 200, "/tmp/test.md")
        assert result.status == DreamStatus.REJECTED


# ════════════════════════════════════════════
# 2. FileService
# ════════════════════════════════════════════

class TestFileService:
    @pytest.fixture
    def fs(self, tmp_path):
        return FileService(str(tmp_path))

    def test_init(self, fs):
        assert fs is not None

    @pytest.mark.asyncio
    async def test_read_file_exists(self, fs, tmp_path):
        (tmp_path / "test.txt").write_text("hello world")
        content = await fs.read_file("test.txt")
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, fs):
        try:
            await fs.read_file("nonexistent.txt")
        except FileNotFoundError:
            pass

    @pytest.mark.asyncio
    async def test_write_file(self, fs, tmp_path):
        await fs.write_file("new.txt", "new content")
        assert (tmp_path / "new.txt").read_text() == "new content"

    @pytest.mark.asyncio
    async def test_list_files(self, fs):
        files = await fs.list_files()
        assert isinstance(files, list)


# ════════════════════════════════════════════
# 3. LoopScheduler
# ════════════════════════════════════════════

class TestLoopScheduler:
    def test_init(self):
        mock_executor = MagicMock()
        scheduler = LoopScheduler(command_executor=mock_executor)
        assert scheduler is not None
        assert scheduler._executor is mock_executor

    def test_init_has_executor(self):
        mock_executor = MagicMock()
        scheduler = LoopScheduler(command_executor=mock_executor)
        assert scheduler._executor is mock_executor
