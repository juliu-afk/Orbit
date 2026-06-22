"""Step 1.2 三图谱 Schema 测试。

验证：
- 三组表（code_nodes / db_nodes / config_nodes）+ edges 表存在
- 公共字段（id/name/type/meta/created_at）在所有节点表
- 边表联合索引存在
- 无外键约束（物理隔离）
"""
from __future__ import annotations

from sqlalchemy import inspect

from orbit.graph.models.nodes import (
    Base,
    CodeNode,
    ConfigNode,
    DbNode,
    Edge,
)


def test_three_graph_tables_exist():
    """三图谱各自独立表。"""
    table_names = set(Base.metadata.tables.keys())
    assert "code_nodes" in table_names
    assert "db_nodes" in table_names
    assert "config_nodes" in table_names
    assert "edges" in table_names


def test_common_node_fields():
    """所有节点表继承 BaseNode 的 5 个公共字段。"""
    common = {"id", "name", "type", "meta", "created_at"}
    for model in (CodeNode, DbNode, ConfigNode):
        cols = {c.name for c in inspect(model).columns}
        assert common.issubset(cols), f"{model.__name__} 缺少公共字段"


def test_code_node_specific_fields():
    cols = {c.name for c in inspect(CodeNode).columns}
    assert {"file_path", "start_line", "end_line"}.issubset(cols)


def test_db_node_specific_fields():
    cols = {c.name for c in inspect(DbNode).columns}
    # schema 字段名（数据库列名就是 schema）
    assert "schema" in cols
    assert "db_type" in cols


def test_config_node_specific_fields():
    cols = {c.name for c in inspect(ConfigNode).columns}
    assert {"hash", "file_path", "env"}.issubset(cols)


def test_edge_node_type_fields():
    """边表含 source/target_node_type（跨图谱软关联）。"""
    cols = {c.name for c in inspect(Edge).columns}
    assert {"source_id", "source_node_type", "target_id", "target_node_type"}.issubset(
        cols
    )


def test_no_foreign_keys():
    """WHY 物理隔离：所有表无外键约束（Step 1.2 范围 Don't）。"""
    for table in Base.metadata.tables.values():
        fks = list(table.foreign_keys)
        assert not fks, f"{table.name} 不应有外键约束，但有 {fks}"


def test_edge_indexes():
    """edges 表有 source/target + edge_type 联合索引（图谱查询高频）。"""
    table = Base.metadata.tables["edges"]
    index_names = {idx.name for idx in table.indexes}
    assert "idx_edges_source_type" in index_names
    assert "idx_edges_target_type" in index_names