"""/dream 模块测试 (Phase 2 AC10)."""

from __future__ import annotations

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
