"""三图谱 SQLAlchemy 2.0 ORM 模型。

WHY 三图谱物理隔离（无外键约束）：代码/数据库/配置图谱各自独立演进，
避免一个图谱的 Schema 变更连锁影响其他图谱。跨图谱关系通过 edges 表
按 node_type 软关联，查询时显式 JOIN。

设计依据：PRD+ADR Step 1.2 数据契约。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """所有模型的声明基类。Alembic 以 Base.metadata 为迁移目标。"""


class BaseNode:
    """三图谱节点公共字段（混入，非独立表）。

    WHY 用混入而不是 abstract 表：三组表字段差异大但共享 5 个公共字段，
    混入比 Joined Table Inheritance 更简单，避免生成不必要的 JOIN。
    """

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # meta 存非结构化扩展属性（如函数签名、表注释），JSON 灵活无需改表
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class CodeNode(Base, BaseNode):
    """代码图谱节点：函数/类/模块/变量等源码符号。

    数据来源：Tree-sitter 解析源码（Step 3.1）。
    Phase 3: parent_id ——节点层级（Module→Class→Method）。
    """

    __tablename__ = "code_nodes"

    file_path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    # Phase 3: 节点层级——父节点引用（Module/Class/Function 嵌套）
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class DbNode(Base, BaseNode):
    """数据库图谱节点：表/视图/字段/存储过程。

    数据来源：DDL 解析 + SQLLineage（Step 3.2）。
    """

    __tablename__ = "db_nodes"

    # 数据库列名保留为 schema（SQLAlchemy 允许列名为 schema，与 Python 关键字无关）
    schema_name: Mapped[str | None] = mapped_column("schema", String(128))
    db_type: Mapped[str | None] = mapped_column(String(50))  # table / view / column


class ConfigNode(Base, BaseNode):
    """配置图谱节点：环境变量/Nginx 指令/PHP.ini/docker-compose 项。

    数据来源：configparser + pyyaml + dotenv（Step 3.3）。
    hash 用于检测配置漂移（Step L8）。
    """

    __tablename__ = "config_nodes"

    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    env: Mapped[str | None] = mapped_column(String(50))


class Edge(Base):
    """统一边表：跨图谱关系（calls/inherits/references/depends）。

    WHY 单表存所有边 + node_type 软关联：三图谱物理隔离，外键无法跨表约束。
    source_node_type 字段标识源节点属于哪个图谱，查询时显式路由到对应表。
    """

    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_node_type: Mapped[str] = mapped_column(String(20), nullable=False)  # code/db/config
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    weight: Mapped[float | None] = mapped_column(Float)  # 可选：调用频次/置信度
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        # WHY 联合索引：图谱查询高频模式是"某节点的某类型出边/入边"
        Index("idx_edges_source_type", "source_id", "edge_type"),
        Index("idx_edges_target_type", "target_id", "edge_type"),
    )
