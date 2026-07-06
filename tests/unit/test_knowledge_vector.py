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
        if vector._use_turbovec:
            assert vector._index is not None
            assert len(vector._concepts) == 10
        else:
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
        assert len([t for t in tokens if len(t) == 2]) > 0
        assert "currentratio" in tokens or "current" in tokens

    def test_empty_text(self) -> None:
        tokens = _tokenize("")
        assert tokens == []

    def test_numbers_and_symbols(self) -> None:
        tokens = _tokenize("123 456 @#$ test")
        # 英文部分会被提取
        assert "test" in tokens


# -- 覆盖缺口: _compute_tf + _cosine_similarity --


class TestTFIDFInternals:
    def test_compute_tf_normal(self):
        from orbit.knowledge.vector import VectorStore
        tokens = ["a", "b", "a", "c", "a"]
        tf = VectorStore._compute_tf(tokens)
        assert tf["a"] == 1.0  # 最高频 → 1.0
        assert tf["b"] == 1.0 / 3
        assert tf["c"] == 1.0 / 3

    def test_compute_tf_single(self):
        from orbit.knowledge.vector import VectorStore
        tf = VectorStore._compute_tf(["only"])
        assert tf["only"] == 1.0

    def test_compute_tf_empty(self):
        from orbit.knowledge.vector import VectorStore
        tf = VectorStore._compute_tf([])
        assert tf == {}

    def test_cosine_identical(self):
        from orbit.knowledge.vector import VectorStore
        v = VectorStore.__new__(VectorStore)
        v._idf = {"a": 1.0, "b": 1.0}
        tf = {"a": 1.0, "b": 0.5}
        sim = v._cosine_similarity(tf, tf)
        assert 0.99 < sim <= 1.0

    def test_cosine_disjoint(self):
        from orbit.knowledge.vector import VectorStore
        v = VectorStore.__new__(VectorStore)
        v._idf = {}
        sim = v._cosine_similarity({"a": 1.0}, {"b": 1.0})
        assert sim == 0.0

    def test_cosine_empty_query(self):
        from orbit.knowledge.vector import VectorStore
        v = VectorStore.__new__(VectorStore)
        v._idf = {"a": 1.0}
        sim = v._cosine_similarity({}, {"a": 1.0})
        assert sim == 0.0


class TestVectorStoreEdgeCases:
    @pytest.fixture
    def empty_vector(self) -> VectorStore:
        import tempfile
        from pathlib import Path
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        # 不初始化——空库
        v = VectorStore.__new__(VectorStore)
        v._store = store
        v._documents = {}
        v._idf = {}
        v._use_turbovec = False
        v._index = None
        v._embedder = None
        v._concepts = []
        return v

    def test_search_empty_store(self, empty_vector):
        """空索引 → 搜索返回空。"""
        results = empty_vector.search("anything")
        assert results == []

    def test_search_no_tokens(self, empty_vector):
        """查询无有效 token → 空。"""
        empty_vector._documents = {"test": {"tf": {}, "name_zh": "", "definition": "", "formula": "", "source_uri": ""}}
        empty_vector._idf = {}
        results = empty_vector.search("123")  # 无中文/英文
        assert results == []
