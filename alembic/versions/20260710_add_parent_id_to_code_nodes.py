"""Phase 3: 节点层级——CodeNode 新增 parent_id 字段。

Revision ID: 20260710_parent_id
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260710_parent_id"
down_revision: str | None = "20260707_add_severity_to_review_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "code_nodes",
        sa.Column("parent_id", sa.String(36), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("code_nodes", "parent_id")
