"""Step 3.4a KnowledgeStore 单元测试。"""

import tempfile
from pathlib import Path

import pytest

from orbit.knowledge.store import KnowledgeStore


class TestKnowledgeStore:
    """SQLite 知识存储——CRUD + 种子数据。"""

    @pytest.fixture
    def store(self) -> KnowledgeStore:
        """独立 DB——临时文件，teardown 清理。"""
        path = Path(tempfile.mktemp(suffix=".db"))
        s = KnowledgeStore(db_path=path)
        s.initialize()
        yield s
        s.close(cleanup=True)

    def test_initialize_creates_table(self, store: KnowledgeStore) -> None:
        """建表 + 种子数据插入成功。"""
        assert store.count() == 10

    def test_initialize_is_idempotent(self, store: KnowledgeStore) -> None:
        """重复 initialize 不报错，不重复插入。"""
        store.initialize()
        assert store.count() == 10

    def test_query_exact_found(self, store: KnowledgeStore) -> None:
        """精确查询返回正确概念。"""
        result = store.query_exact("accounting", "CurrentRatio")
        assert result is not None
        assert result["name_zh"] == "流动比率"
        assert "流动资产 / 流动负债" in result["formula"]
        assert result["source_uri"].startswith("standard://")
        assert result["source_level"] == 2

    def test_query_exact_not_found(self, store: KnowledgeStore) -> None:
        """不存在的概念返回 None。"""
        result = store.query_exact("accounting", "NonExistent")
        assert result is None

    def test_query_exact_wrong_domain(self, store: KnowledgeStore) -> None:
        """错误的 domain 返回 None。"""
        result = store.query_exact("finance", "CurrentRatio")
        assert result is None

    def test_list_by_domain(self, store: KnowledgeStore) -> None:
        """按领域列出所有概念。"""
        concepts = store.list_by_domain("accounting")
        assert len(concepts) == 10
        # 按 source_level 排序：IFRS(level=1) 在前，CAS(level=2) 在后
        names = [c["name_zh"] for c in concepts]
        assert "资产负债率" in names  # IFRS level 1

    def test_list_empty_domain(self, store: KnowledgeStore) -> None:
        """无概念的领域返回空列表。"""
        concepts = store.list_by_domain("medical")
        assert concepts == []

    def test_source_level_range(self, store: KnowledgeStore) -> None:
        """所有 source_level 在 1-5 范围内。"""
        for c in store.list_by_domain("accounting"):
            result = store.query_exact("accounting", c["concept"])
            assert 1 <= result["source_level"] <= 5

    def test_count_accurate(self, store: KnowledgeStore) -> None:
        """count() 返回准确数。"""
        assert store.count() == len([c for c in store.list_by_domain("accounting")])
