"""Step 3.2 数据库图谱引擎测试。

用内存 SQLite + SQLAlchemy 反射测试。
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from orbit.graph.engines.db_graph import DbGraphEngine
from orbit.graph.models.nodes import Base

# 测试用 ORM 模型（建真实表测反射）
_TestModelsBase = declarative_base()


class User(_TestModelsBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))


class Order(_TestModelsBase):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Integer)


@pytest.fixture
async def setup_db():
    """建测试库 + 图谱 session。"""
    db_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with db_engine.begin() as conn:
        await conn.run_sync(_TestModelsBase.metadata.create_all)
    graph_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with graph_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(graph_engine, expire_on_commit=False)
    yield db_engine, session_factory
    await db_engine.dispose()
    await graph_engine.dispose()


@pytest.fixture
async def db_engine(setup_db):
    return DbGraphEngine(session_factory=setup_db[1], db_engine=setup_db[0])


@pytest.mark.asyncio
async def test_build_index(db_engine):
    """反射数据库提取表。"""
    count = await db_engine.build_index()
    assert count == 2  # users + orders


@pytest.mark.asyncio
async def test_table_exists(db_engine):
    """SC1: table_exists 查询。"""
    await db_engine.build_index()
    assert await db_engine.table_exists("users") is True
    assert await db_engine.table_exists("orders") is True
    assert await db_engine.table_exists("nonexistent") is False


@pytest.mark.asyncio
async def test_get_tables(db_engine):
    """获取所有表名。"""
    await db_engine.build_index()
    tables = await db_engine.get_tables()
    assert "users" in tables
    assert "orders" in tables


@pytest.mark.asyncio
async def test_get_foreign_keys(db_engine):
    """SC2: 外键关系准确。orders.user_id → users.id。"""
    await db_engine.build_index()
    fks = await db_engine.get_foreign_keys("orders")
    assert any(fk["column"] == "user_id" and fk["ref_table"] == "users" for fk in fks)


@pytest.mark.asyncio
async def test_column_exists(db_engine):
    """P2-1: 字段存在查询 column_exists。"""
    await db_engine.build_index()
    # users 表有 id/name 列
    assert await db_engine.column_exists("users", "id") is True
    assert await db_engine.column_exists("users", "name") is True
    assert await db_engine.column_exists("users", "nonexistent") is False


@pytest.mark.asyncio
async def test_no_foreign_keys_for_users(db_engine):
    """users 表无外键。"""
    await db_engine.build_index()
    fks = await db_engine.get_foreign_keys("users")
    assert fks == []
