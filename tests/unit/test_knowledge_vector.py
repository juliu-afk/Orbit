"""Step 3.4c VectorStore 单元测试。"""

import tempfile
from pathlib import Path

import pytest

from orbit.knowledge.store import KnowledgeStore
from orbit.knowledge.vector import VectorStore, _tokenize


class TestVectorStore:
    """TF-IDF 向量存储——索引构建 + 语义搜索。"""

    @pytest.fixture
    def vector(self) -> VectorStore:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        v = VectorStore(store=store)
        yield v
        store.close(cleanup=True)

    def test_index_built(self, vector: VectorStore) -> None:
        """索引构建成功——所有概念可搜索。"""
        assert len(vector._documents) == 10
        assert len(vector._idf) > 0

    def test_search_exact_concept(self, vector: VectorStore) -> None:
        """搜索"流动比率"——应返回 CurrentRatio 为高分结果。"""
        results = vector.search("流动比率")
        assert len(results) > 0
        # CurrentRatio 应为 top 结果
        concepts = [r["concept"] for r in results]
        assert "CurrentRatio" in concepts

    def test_search_semantic_query(self, vector: VectorStore) -> None:
        """自然语言查询——"盈利能力"应匹配 ROE 或毛利率。"""
        results = vector.search("盈利能力")
        assert len(results) > 0
        concepts = [r["concept"] for r in results]
        # ROE 或 GrossProfitMargin 应为高分
        assert any(c in ("ROE", "GrossProfitMargin") for c in concepts)

    def test_search_empty_query(self, vector: VectorStore) -> None:
        """空查询返回空列表。"""
        assert vector.search("") == []

    def test_search_score_range(self, vector: VectorStore) -> None:
        """score 在 0-1 范围内。"""
        results = vector.search("偿债能力")
        for r in results:
            assert 0.0 <= r["score"] <= 1.0

    def test_search_result_has_source_uri(self, vector: VectorStore) -> None:
        """每个搜索结果含 source_uri。"""
        results = vector.search("资产负债表")
        for r in results:
            assert r["source_uri"].startswith("standard://")


class TestTokenize:
    """中文分词——bigram + 英文单词。"""

    def test_chinese_bigram(self) -> None:
        tokens = _tokenize("流动比率")
        assert "流动" in tokens or "动比" in tokens or "比率" in tokens

    def test_english_words(self) -> None:
        tokens = _tokenize("EBITDA ROE revenue")
        assert "ebitda" in tokens
        assert "roe" in tokens
        assert "revenue" in tokens

    def test_mixed_text(self) -> None:
        tokens = _tokenize("流动比率 CurrentRatio")
        # 含中文 bigram
        assert len([t for t in tokens if len(t) == 2]) > 0
        # 含英文小写
        assert "currentratio" in tokens or "current" in tokens
