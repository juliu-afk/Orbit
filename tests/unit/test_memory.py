"""记忆模块单元测试 (Phase 2 AC9)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from orbit.memory.cjk import build_fts_query, tokenize_for_fts
from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore


class TestCJKTokenizer:
    def test_cjk_bigram(self):
        result = tokenize_for_fts("上下文压缩")
        assert "上下" in result
        assert "下文" in result
        assert "文压" in result
        assert "压缩" in result

    def test_mixed_cjk_english(self):
        result = tokenize_for_fts("Agent 记忆系统 test")
        assert "agent" in result
        assert "记忆" in result or "忆系" in result
        assert "test" in result

    def test_empty(self):
        assert tokenize_for_fts("") == ""

    def test_single_cjk(self):
        result = tokenize_for_fts("好")
        assert "好" in result

    def test_build_fts_query(self):
        result = build_fts_query("搜索记忆")
        assert "搜索" in result or "索记" in result


class TestMemoryStore:
    @pytest.fixture
    def tmp_store(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "project"
            project.mkdir()
            store = MemoryStore(project_path=str(project))
            yield store

    def test_write_and_read(self, tmp_store):
        tmp_store.write_file(MemoryFileType.EPISODIC, "## Test\nhello world")
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert "hello world" in mem.body
        assert mem.checksum_sha256

    def test_append(self, tmp_store):
        tmp_store.write_file(MemoryFileType.EPISODIC, "first entry\n")
        tmp_store.append_to_file(MemoryFileType.EPISODIC, "second entry")
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert "first" in mem.body
        assert "second" in mem.body

    def test_search(self, tmp_store):
        tmp_store.write_file(
            MemoryFileType.EPISODIC, "Agent learned about Decimal\nAgent fixed bug-42\n"
        )
        results = tmp_store.search(
            __import__("orbit.memory.models", fromlist=["MemorySearchQuery"]).MemorySearchQuery(
                query="Decimal"
            )
        )
        assert len(results) > 0
        assert any("Decimal" in r.snippet for r in results)

    def test_read_nonexistent(self, tmp_store):
        mem = tmp_store.read_file(MemoryFileType.NOTES)
        assert mem.body == ""

    def test_frontmatter_parsing(self, tmp_store):
        tmp_store.write_file(
            MemoryFileType.EPISODIC,
            "body content",
            frontmatter={"type": "episodic", "version": "1"},
        )
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert mem.frontmatter.get("type") == "episodic"
        assert "body content" in mem.body

    def test_read_for_agent(self, tmp_store):
        tmp_store.write_file(
            MemoryFileType.EPISODIC,
            "##通用规则\nall agents\n##Developer\ncode tips\n##Architect\ndesign tips\n",
        )
        mem = tmp_store.read_for_agent("developer")
        assert "通用" in mem.body or "developer" in mem.body.lower()


class TestMemoryScoring:
    """Phase 1: Memory 评分（hit + decay）。"""

    @pytest.fixture
    def tmp_store(self, tmp_path):
        from orbit.memory.store import MemoryStore

        store = MemoryStore(str(tmp_path))
        # Phase 1: 扁平化前端存储——score.{key}: value
        store.write_file(
            MemoryFileType.EPISODIC,
            "## Section A\nmemory alpha\n## Section B\nmemory beta\n",
            frontmatter={"score.key-a": "3.0", "score.key-b": "1.0"},
        )
        return store

    def test_hit_increases_score(self, tmp_store):
        """hit() 应增加指定 key 的评分。"""
        tmp_store.hit("key-b", delta=1.0)
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert mem.frontmatter["score.key-b"] == "2.0"  # 1.0 + 1.0
        assert mem.frontmatter["score.key-a"] == "3.0"  # unchanged

    def test_hit_creates_new_score(self, tmp_store):
        """hit() 对不存在的 key 应创建评分。"""
        tmp_store.hit("key-new", delta=1.0)
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        # frontmatter 值均为字符串（简单解析器）
        assert float(mem.frontmatter["score.key-new"]) == 2.0  # default 1.0 + 1.0

    def test_decay_reduces_all_scores(self, tmp_store):
        """decay_scores() 应降低所有评分条目。"""
        count = tmp_store.decay_scores(factor=0.5)
        assert count == 2
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert float(mem.frontmatter["score.key-a"]) == 1.5  # 3.0 * 0.5
        assert float(mem.frontmatter["score.key-b"]) == 0.5  # 1.0 * 0.5

    def test_decay_floor(self, tmp_store):
        """decay_scores() 不低于 min=0.1。"""
        tmp_store.hit("key-b", delta=-0.95)  # 1.0 - 0.95 = 0.05 → 会被 clamp
        tmp_store.decay_scores(factor=0.5)
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert float(mem.frontmatter["score.key-b"]) >= 0.1  # floor

    def test_score_stored_in_frontmatter(self, tmp_store):
        """评分应持久化在 frontmatter 中，格式为 score.{key}。"""
        mem = tmp_store.read_file(MemoryFileType.EPISODIC)
        assert "score.key-a" in mem.frontmatter
        assert "score.key-b" in mem.frontmatter

    def test_search_result_has_entry_score_field(self):
        """MemorySearchResult 应有 entry_score 字段。"""
        from orbit.memory.models import MemorySearchResult

        r = MemorySearchResult(path="/x", score=0.8, snippet="test", entry_score=2.5)
        assert r.entry_score == 2.5


class TestDreamVerifier:
    def test_pass(self):
        from orbit.dream.models import DreamConfig
        from orbit.dream.verifier import DreamVerifier

        verifier = DreamVerifier(DreamConfig(max_output_lines=200, max_output_bytes=10_240))
        result = verifier.verify("small content", "/tmp/test.md")
        assert result.status == "complete"
        assert result.lines == 1

    def test_reject_too_many_lines(self):
        from orbit.dream.models import DreamConfig
        from orbit.dream.verifier import DreamVerifier

        verifier = DreamVerifier(DreamConfig(max_output_lines=5, max_output_bytes=10_240))
        content = "\n".join(str(i) for i in range(10))
        result = verifier.verify(content, "/tmp/test.md")
        assert result.status == "rejected"
        assert "行数" in result.verification_message

    def test_reject_too_many_bytes(self):
        from orbit.dream.models import DreamConfig
        from orbit.dream.verifier import DreamVerifier

        verifier = DreamVerifier(DreamConfig(max_output_lines=200, max_output_bytes=50))
        result = verifier.verify("x" * 100, "/tmp/test.md")
        assert result.status == "rejected"
        assert "字节" in result.verification_message
