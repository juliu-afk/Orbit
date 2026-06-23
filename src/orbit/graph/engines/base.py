"""图谱引擎基类（Step 3.x 共用）。

三图谱共用同一套存储模型（CodeNode/DbNode/ConfigNode/Edge），
但物理隔离（无外键）。各引擎只负责"解析源 → 生成 Node/Edge → 写入"。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orbit.graph.models.nodes import Edge


class GraphEngineBase:
    """图谱引擎基类，提供节点/边的通用读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def upsert_node(self, model: type, node_id: str, **fields: Any) -> Any:
        """插入或更新节点（按 id upsert）。"""
        async with self.session_factory() as session:  # type: ignore[func-returns-value]
            existing = await session.get(model, node_id)
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                node = model(id=node_id, **fields)
                session.add(node)
            await session.commit()
            return await session.get(model, node_id)

    async def delete_nodes_by_file(self, model: type, file_path: str) -> int:
        """删除某文件的所有节点（增量更新前清理旧数据）。

        PR#5 P1-1：必须同时清理关联的 Edge，否则残留边指向已删节点，
        导致 get_callers/get_callees 返回错误结果。
        """
        from sqlalchemy import delete as sa_delete

        async with self.session_factory() as session:
            result: Any = await session.execute(select(model).where(model.file_path == file_path))  # type: ignore[attr-defined]
            nodes = result.scalars().all()
            node_ids = [n.id for n in nodes]
            if node_ids:
                await session.execute(
                    sa_delete(Edge).where(
                        Edge.source_id.in_(node_ids) | Edge.target_id.in_(node_ids)
                    )
                )
            for node in nodes:
                await session.delete(node)
            await session.commit()
            return len(nodes)

    async def find_node_by_name(
        self, model: type, name: str, namespace: str | None = None
    ) -> Any | None:
        """按名称（+ 可选命名空间）查找节点。"""
        async with self.session_factory() as session:
            stmt: Any = select(model).where(model.name == name)  # type: ignore[attr-defined]
            if namespace is not None:
                stmt = stmt.where(model.meta["namespace"].as_string() == namespace)  # type: ignore[attr-defined]
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def add_edge(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        edge_type: str,
    ) -> None:
        """添加边（调用/依赖等关系）。"""
        async with self.session_factory() as session:
            edge = Edge(
                source_id=source_id,
                source_node_type=source_type,
                target_id=target_id,
                target_node_type=target_type,
                edge_type=edge_type,
            )
            session.add(edge)
            await session.commit()

    async def get_edges(self, node_id: str, edge_type: str, direction: str = "out") -> list[Edge]:
        """查询节点的边。direction: out=出边，in=入边。"""
        async with self.session_factory() as session:
            col = Edge.source_id if direction == "out" else Edge.target_id
            result = await session.execute(
                select(Edge).where(col == node_id, Edge.edge_type == edge_type)
            )
            return list(result.scalars().all())

    async def clear_all(self, model: type) -> int:
        """清空某图谱的所有节点（重建索引用）。"""
        async with self.session_factory() as session:
            from sqlalchemy import delete as sa_delete

            result = await session.execute(sa_delete(model))
            await session.commit()
            return result.rowcount or 0  # type: ignore[attr-defined]
