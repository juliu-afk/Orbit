"""Step 3.4b KnowledgeEngine 单元测试。"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from orbit.knowledge.engine import KnowledgeEngine
from orbit.knowledge.store import KnowledgeStore


class TestKnowledgeEngine:
    """查询引擎——exact 模式 + 降级行为。"""

    @pytest.fixture
    def engine(self) -> Generator[KnowledgeEngine, None, None]:
        """独立 engine——临时 DB。"""
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        yield KnowledgeEngine(store=store)
        store.close(cleanup=True)

    def test_query_exact_returns_result(self, engine: KnowledgeEngine) -> None:
        """精确查询 CurrentRatio 返回完整结果。"""
        result = engine.query("accounting", "CurrentRatio")
        assert result is not None
        assert "流动比率" in result.content
        assert "流动资产 / 流动负债" in result.content
        assert result.confidence == 1.0
        assert result.mode_used == "exact"
        assert result.source_uri.startswith("standard://")

    def test_query_exact_not_found(self, engine: KnowledgeEngine) -> None:
        """不存在的概念返回 None。"""
        result = engine.query("accounting", "NonExistent")
        assert result is None

    def test_query_semantic_degraded_to_exact(self, engine: KnowledgeEngine) -> None:
        """semantic 模式降级为 exact（3.4c 前预期行为）。"""
        result = engine.query("accounting", "ROE", mode="semantic")
        assert result is not None
        assert result.mode_used == "semantic"  # 保留请求模式
        assert "净资产收益率" in result.content

    def test_query_hybrid_degraded_to_exact(self, engine: KnowledgeEngine) -> None:
        """hybrid 模式降级为 exact。"""
        result = engine.query("accounting", "EBITDA", mode="hybrid")
        assert result is not None
        assert "息税折旧摊销前利润" in result.content

    def test_list_concepts_returns_all(self, engine: KnowledgeEngine) -> None:
        """列出会计领域 10 个概念。"""
        concepts = engine.list_concepts("accounting")
        assert len(concepts) == 10

    def test_count(self, engine: KnowledgeEngine) -> None:
        """count 返回 10。"""
        assert engine.count() == 10

    def test_query_result_to_dict(self, engine: KnowledgeEngine) -> None:
        """QueryResult.to_dict() 输出正确格式。"""
        result = engine.query("accounting", "DoubleEntry")
        assert result is not None
        d = result.to_dict()
        assert d["confidence"] == 1.0
        assert "复式记账" in d["content"]
        assert d["source_uri"].startswith("standard://")
