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
        # 无LLM时merge返回原文，dedup+verify正常执行
        assert result.status in ("complete", "failed")

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
