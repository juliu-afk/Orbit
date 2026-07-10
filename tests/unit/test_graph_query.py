"""graph/query.py 单元测试——覆盖 GraphQuery 类 + 三种图谱路由 + 错误处理。
覆盖率冲刺 B1-4：0% → ≥80%。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.graph.query import GraphQuery


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def code_graph():
    """返回 mock CodeGraphEngine。"""
    cg = MagicMock()
    cg.find_definitions_with_positions = AsyncMock()
    cg.get_all_nodes = AsyncMock()
    return cg


@pytest.fixture
def db_graph():
    """返回 mock DbGraphEngine。"""
    dg = MagicMock()
    dg.table_exists = AsyncMock()
    return dg


@pytest.fixture
def config_graph():
    """返回 mock ConfigGraphEngine。"""
    cg = MagicMock()
    cg.get_config = MagicMock()
    return cg


# ── 构造 ──────────────────────────────────────────────────


class TestGraphQueryInit:
    """测试 __init__ 和依赖注入。"""

    def test_no_engines(self):
        """无引擎注入——属性全为 None。"""
        q = GraphQuery()
        assert q._code is None
        assert q._db is None
        assert q._config is None

    def test_all_engines(self, code_graph, db_graph, config_graph):
        """三引擎全注入。"""
        q = GraphQuery(code_graph=code_graph, db_graph=db_graph, config_graph=config_graph)
        assert q._code is code_graph
        assert q._db is db_graph
        assert q._config is config_graph


# ── query("code") ─────────────────────────────────────────


class TestQueryCode:
    """测试 graph_type="code" 查询。"""

    @pytest.mark.asyncio
    async def test_no_code_graph(self):
        """未注入 code_graph——返回错误。"""
        q = GraphQuery()
        result = await q.query("code", symbol="foo")
        assert result["found"] is False
        assert "CodeGraph 未初始化" in result["error"]

    @pytest.mark.asyncio
    async def test_symbol_lookup(self, code_graph):
        """按符号查询——返回定义和位置。"""
        code_graph.find_definitions_with_positions.return_value = [{"name": "foo", "file": "a.py", "line": 10}]
        q = GraphQuery(code_graph=code_graph)
        result = await q.query("code", symbol="foo")
        assert result["found"] is True
        assert result["type"] == "code"
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_symbol_not_found(self, code_graph):
        """符号不存在——found=False。"""
        code_graph.find_definitions_with_positions.return_value = []
        q = GraphQuery(code_graph=code_graph)
        result = await q.query("code", symbol="nonexistent")
        assert result["found"] is False
        assert result["type"] == "code"

    @pytest.mark.asyncio
    async def test_no_symbol_returns_overview(self, code_graph):
        """无 symbol——返回架构概览（节点数）。"""
        code_graph.get_all_nodes.return_value = [1, 2, 3]
        q = GraphQuery(code_graph=code_graph)
        result = await q.query("code")
        assert result["found"] is True
        assert result["data"]["node_count"] == 3


# ── query("database") ─────────────────────────────────────


class TestQueryDatabase:
    """测试 graph_type="database" 查询。"""

    @pytest.mark.asyncio
    async def test_no_db_graph(self):
        """未注入 db_graph——返回错误。"""
        q = GraphQuery()
        result = await q.query("database", table="users")
        assert result["found"] is False
        assert "DbGraph 未初始化" in result["error"]

    @pytest.mark.asyncio
    async def test_table_exists(self, db_graph):
        """表存在——found=True。"""
        db_graph.table_exists.return_value = True
        q = GraphQuery(db_graph=db_graph)
        result = await q.query("database", table="users")
        assert result["found"] is True
        assert result["data"]["table"] == "users"

    @pytest.mark.asyncio
    async def test_table_not_found(self, db_graph):
        """表不存在——found=False。"""
        db_graph.table_exists.return_value = False
        q = GraphQuery(db_graph=db_graph)
        result = await q.query("database", table="ghost")
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_missing_table_param(self, db_graph):
        """未指定 table——返回错误。"""
        q = GraphQuery(db_graph=db_graph)
        result = await q.query("database")
        assert result["found"] is False
        assert "请指定 table 参数" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_table_param(self, db_graph):
        """table 为空字符串——依赖引擎处理。"""
        db_graph.table_exists.return_value = False
        q = GraphQuery(db_graph=db_graph)
        result = await q.query("database", table="")
        assert result["found"] is False


# ── query("config") ───────────────────────────────────────


class TestQueryConfig:
    """测试 graph_type="config" 查询。"""

    @pytest.mark.asyncio
    async def test_no_config_graph(self):
        """未注入 config_graph——返回错误。"""
        q = GraphQuery()
        result = await q.query("config", key="app.port")
        assert result["found"] is False
        assert "ConfigGraph 未初始化" in result["error"]

    @pytest.mark.asyncio
    async def test_key_found(self, config_graph):
        """配置键存在——返回 found=True。"""
        config_graph.get_config.return_value = {"port": 18888}
        q = GraphQuery(config_graph=config_graph)
        result = await q.query("config", key="app.port")
        assert result["found"] is True
        assert result["data"] == {"port": 18888}

    @pytest.mark.asyncio
    async def test_key_not_found(self, config_graph):
        """配置键不存在——get_config 返回 None → found=False。"""
        config_graph.get_config.return_value = None
        q = GraphQuery(config_graph=config_graph)
        result = await q.query("config", key="nonexistent")
        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_missing_key_param(self, config_graph):
        """未指定 key——返回错误。"""
        q = GraphQuery(config_graph=config_graph)
        result = await q.query("config")
        assert result["found"] is False
        assert "请指定 key 参数" in result["error"]


# ── 边缘情况 ──────────────────────────────────────────────


class TestQueryEdgeCases:
    """测试边缘/错误情况。"""

    @pytest.mark.asyncio
    async def test_unknown_graph_type(self):
        """未知图谱类型——返回错误。"""
        q = GraphQuery()
        result = await q.query("unknown")  # type: ignore[arg-type]
        assert result["found"] is False
        assert "未知图谱类型" in result["error"]

    @pytest.mark.asyncio
    async def test_extra_filters_passed(self, code_graph):
        """**filters 传入但不影响 code 路径。"""
        code_graph.find_definitions_with_positions.return_value = []
        q = GraphQuery(code_graph=code_graph)
        result = await q.query("code", symbol="foo", extra_filter=True, limit=10)
        assert result["type"] == "code"
