"""审查模块 SQLAlchemy 2.0 ORM 模型。

WHY 独立 Base：审查模块有自己的 DeclarativeBase，
与 graph 模块的 Base 隔离——Alembic 迁移互不影响。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


class ReviewBase(DeclarativeBase):
    """审查模块声明基类——独立于 graph 模块的 Base。"""


class Review(ReviewBase):
    """审查会话——一个 task 对应一次审查。

    WHY task_id 唯一约束：同一 task 同时只有一个活跃审查会话，
    避免多审查者冲突。
    """

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, unique=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | in_review | changes_requested | approved | merged
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class ReviewDecision(ReviewBase):
    """审查决定——对某个文件某个 hunk 的批准/打回/注释标记。

    WHY hunk_index 而非行号：diff hunk 是审查的最小可操作单元，
    行号在 Agent 修复后发生变化，hunk_index 在审查生命周期内稳定。
    """

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    hunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # approved | rejected | comment
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    review: Mapped["Review"] = relationship(back_populates="decisions")


class ReviewComment(ReviewBase):
    """审查注释——对某文件中某个行范围的评论。

    WHY 分离于 ReviewDecision：注释是对话（创建→Agent修复→关闭），
    决定是二元判定（批准/打回）。生命周期不同——注释有状态流转，
    决定是终态的。
    """

    __tablename__ = "review_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open | in_progress | resolved
    assigned_to: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # agent role or human name
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    review: Mapped["Review"] = relationship(back_populates="comments")
