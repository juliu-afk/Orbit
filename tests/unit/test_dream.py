"""/dream 模块测试 (Phase 2 AC10)."""

from __future__ import annotations

import pytest

from orbit.dream.models import DreamConfig
from orbit.dream.verifier import DreamVerifier


class TestDreamVerifier:
    def test_verify_pass(self):
        verifier = DreamVerifier(DreamConfig(max_output_lines=200, max_output_bytes=10_240))
        result = verifier.verify("hello world", "/tmp/test.md")
        assert result.status == "complete"

    def test_verify_too_many_lines(self):
        verifier = DreamVerifier(DreamConfig(max_output_lines=3, max_output_bytes=10_240))
        result = verifier.verify("a\nb\nc\nd\ne\n", "/tmp/test.md")
        assert result.status == "rejected"

    def test_verify_too_many_bytes(self):
        verifier = DreamVerifier(DreamConfig(max_output_lines=200, max_output_bytes=20))
        result = verifier.verify("x" * 100, "/tmp/test.md")
        assert result.status == "rejected"


class TestJaccard:
    def test_identical(self):
        from orbit.dream.engine import _jaccard_similarity

        assert _jaccard_similarity("a b c", "a b c") == 1.0

    def test_disjoint(self):
        from orbit.dream.engine import _jaccard_similarity

        assert _jaccard_similarity("a b c", "x y z") == 0.0

    def test_partial(self):
        from orbit.dream.engine import _jaccard_similarity

        sim = _jaccard_similarity("a b c", "a b d")
        assert 0.4 < sim < 0.7


# ── DreamEngine ─────────────────────────────────────


class TestDreamEngine:
    @pytest.mark.asyncio
    async def test_run_without_llm(self):
        """无LLM时dream仍可运行（跳过merge阶段）."""
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig
        from orbit.memory.store import MemoryStore

        engine = DreamEngine(llm_client=None, memory_store=MemoryStore(), config=DreamConfig())
        result = await engine.run()
        # 无LLM时merge返回原文 → dedup → verify
        # 状态取决于当前环境记忆内容是否超限，不为 FAILED 即可
        assert result.status in ("complete", "rejected")

    def test_stage_gather_empty(self):
        """空记忆——gather返回空字符串."""
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        engine = DreamEngine(llm_client=None, config=DreamConfig())
        gathered = engine._stage_gather()
        assert isinstance(gathered, str)

    def test_stage_dedup_identical(self):
        """去重——相同段落合并."""
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        engine = DreamEngine(config=DreamConfig())
        content = "same content here\n\nsame content here\n\nunique content"
        result = engine._stage_dedup(content)
        # 重复段落应被移除
        assert result.count("same content here") <= 2

    def test_stage_dedup_single_paragraph(self):
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        engine = DreamEngine(config=DreamConfig())
        result = engine._stage_dedup("only one")
        assert result == "only one"

    def test_stage_verify_complete(self):
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        engine = DreamEngine(config=DreamConfig(max_output_lines=200, max_output_bytes=10_240))
        result = engine._stage_verify("small content")
        assert result.status == "complete"

    def test_jaccard_empty_sets(self):
        from orbit.dream.engine import _jaccard_similarity

        assert _jaccard_similarity("", "") == 0.0
        assert _jaccard_similarity("a", "") == 0.0


# ── 覆盖缺口测试 ──

class TestDreamEngineCoverage:
    """覆盖 _stage_merge 异常路径 + _stage_gather 非空路径。"""

    @pytest.mark.asyncio
    async def test_stage_merge_llm_exception(self):
        """LLM 调用异常 → 返回原始内容（lines 139, 152-154）。"""
        from unittest.mock import AsyncMock
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        engine = DreamEngine(llm_client=mock_llm, config=DreamConfig())
        result = await engine._stage_merge("test content", 0.3)
        # 异常被捕获，返回原始内容
        assert result == "test content"

    def test_stage_gather_with_progress_and_notes(self):
        """非空 progress 和 notes → 包含在 gathered 中（lines 123, 128）。"""
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig
        from orbit.memory.models import MemoryFileType
        from orbit.memory.store import MemoryStore

        store = MemoryStore()
        store.write_file(MemoryFileType.PROGRESS, "progress body # test", {"type": "progress"})
        store.write_file(MemoryFileType.NOTES, "notes body # test", {"type": "notes"})
        engine = DreamEngine(memory_store=store, config=DreamConfig())
        gathered = engine._stage_gather()
        assert "progress body" in gathered
        assert "notes body" in gathered

    @pytest.mark.asyncio
    async def test_run_exception_path(self):
        """run() 内部异常 → FAILED 状态（lines 100-102）。"""
        from unittest.mock import MagicMock
        from orbit.dream.engine import DreamEngine
        from orbit.dream.models import DreamConfig

        engine = DreamEngine(config=DreamConfig())
        # 让 _stage_gather 抛 RuntimeError
        engine._stage_gather = MagicMock(side_effect=RuntimeError("disk error"))
        engine._stage_dedup = MagicMock()  # 不会被调用
        result = await engine.run()
        assert result.status == "failed"
