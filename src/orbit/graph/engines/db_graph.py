"""数据库图谱引擎（Step 3.2）。

用 SQLAlchemy 反射读取数据库元数据（表/字段/外键），
存入 DbNode + Edge 表，提供表/字段/外键的真实查询（防幻觉 SQL 校验）。

WHY 反射而非解析 DDL：反射走 information_schema，准确性最高（PRD ADR）。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from orbit.graph.engines.base import GraphEngineBase
from orbit.graph.models.nodes import DbNode

logger = structlog.get_logger("orbit.graph.db")


class DbGraphError(Exception):
    """数据库图谱错误基类。"""


class DbGraphEngine(GraphEngineBase):
    """数据库图谱引擎：反射 DB 元数据，提供表/字段/外键查询。

    查询接口：
    - table_exists(name) → bool
    - column_exists(table, column) → bool
    - get_foreign_keys(table) → list[dict]
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        db_engine: AsyncEngine,
        schema: str | None = None,
    ):
        super().__init__(session_factory)
        self.db_engine = db_engine
        self.schema = schema

    async def build_index(self) -> int:
        """反射数据库，提取表/字段/外键，存入 DbNode。返回表数。"""
        async with self.db_engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names(self.schema)
            )
            for table in table_names:
                await self._index_table(conn, table)
        logger.info("db_graph_indexed", tables=len(table_names), schema=self.schema)
        return len(table_names)

    async def _index_table(self, conn: Any, table_name: str) -> None:
        """索引单张表的字段和外键。"""
        columns = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns(table_name, schema=self.schema)
        )
        fks = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys(table_name, schema=self.schema)
        )

        # 表级节点
        table_node_id = uuid.uuid4().hex
        await self.upsert_node(
            DbNode,
            table_node_id,
            name=table_name,
            type="table",
            db_type="table",
            schema_name=self.schema,
            meta={"columns": [c["name"] for c in columns]},
        )

        # 字段级节点
        for col in columns:
            col_id = uuid.uuid4().hex
            await self.upsert_node(
                DbNode,
                col_id,
                name=col["name"],
                type="column",
                db_type="column",
                schema_name=self.schema,
                meta={
                    "table": table_name,
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                },
            )
            # 字段 → 表的依赖边
            await self.add_edge(
                source_id=col_id,
                source_type="db",
                target_id=table_node_id,
                target_type="db",
                edge_type="belongs_to",
            )

        # 外键边
        for fk in fks:
            await self._record_foreign_key(table_name, fk)

    async def _record_foreign_key(self, table: str, fk: dict[str, Any]) -> None:
        """记录外键关系为边。"""
        # fk 格式：{constrained_columns: [...], referred_table: ..., referred_columns: [...]}
        constrained = fk.get("constrained_columns", [])
        referred_table = fk.get("referred_table", "")
        referred_cols = fk.get("referred_columns", [])
        # 记录到表的 meta（简化：存外键信息到表节点）
        table_node = await self.find_node_by_name(DbNode, table)
        if table_node:
            fks_meta = table_node.meta.get("foreign_keys", [])
            for i, col in enumerate(constrained):
                fks_meta.append(
                    {
                        "column": col,
                        "ref_table": referred_table,
                        "ref_column": referred_cols[i] if i < len(referred_cols) else None,
                    }
                )
            table_node.meta["foreign_keys"] = fks_meta
            async with self.session_factory() as session:
                await session.merge(table_node)
                await session.commit()

    # ---- 查询接口 ----

    async def table_exists(self, table_name: str) -> bool:
        """SC1: 表是否存在。"""
        node = await self.find_node_by_name(DbNode, table_name)
        return node is not None

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        """字段是否存在。"""
        async with self.session_factory() as session:
            stmt = select(DbNode).where(
                DbNode.name == column_name,
                DbNode.type == "column",
                DbNode.meta["table"].as_string() == table_name,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        """SC2: 获取表的外键关系。

        返回 [{column, ref_table, ref_column}, ...]
        """
        node = await self.find_node_by_name(DbNode, table_name)
        if node is None:
            return []
        result = node.meta.get("foreign_keys", [])
        assert isinstance(result, list), f"DB foreign_keys 应为 list 类型，实际 {type(result)}"
        return result

    async def get_tables(self) -> list[str]:
        """获取所有表名。"""
        async with self.session_factory() as session:
            stmt = select(DbNode).where(DbNode.type == "table")
            result = await session.execute(stmt)
            return [n.name for n in result.scalars().all()]
