"""Step 3.4a KnowledgeStore 单元测试。"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from orbit.knowledge.store import KnowledgeStore


class TestKnowledgeStore:
    """SQLite 知识存储——CRUD + 种子数据。"""

    @pytest.fixture
    def store(self) -> Generator[KnowledgeStore, None, None]:
        """独立 DB——临时文件，teardown 清理。"""
        path = Path(tempfile.mktemp(suffix=".db"))
        s = KnowledgeStore(db_path=path)
        s.initialize()
        yield s
        s.close(cleanup=True)

    def test_initialize_creates_table(self, store: KnowledgeStore) -> None:
        assert store.count() == 10

    def test_initialize_is_idempotent(self, store: KnowledgeStore) -> None:
        store.initialize()
        assert store.count() == 10

    def test_query_exact_found(self, store: KnowledgeStore) -> None:
        result = store.query_exact("accounting", "CurrentRatio")
        assert result is not None
        assert result["name_zh"] == "流动比率"
        assert "流动资产 / 流动负债" in result["formula"]

    def test_query_exact_not_found(self, store: KnowledgeStore) -> None:
        assert store.query_exact("accounting", "NonExistent") is None

    def test_query_exact_wrong_domain(self, store: KnowledgeStore) -> None:
        assert store.query_exact("finance", "CurrentRatio") is None

    def test_list_by_domain(self, store: KnowledgeStore) -> None:
        concepts = store.list_by_domain("accounting")
        assert len(concepts) == 10

    def test_list_empty_domain(self, store: KnowledgeStore) -> None:
        assert store.list_by_domain("medical") == []

    def test_source_level_range(self, store: KnowledgeStore) -> None:
        for c in store.list_by_domain("accounting"):
            result = store.query_exact("accounting", c["concept"])
            assert result is not None
            assert 1 <= result["source_level"] <= 5

    def test_count_accurate(self, store: KnowledgeStore) -> None:
        assert store.count() == len(store.list_by_domain("accounting"))
