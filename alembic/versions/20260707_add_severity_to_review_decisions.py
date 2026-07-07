"""add severity to review_decisions

Revision: 20260707_severity
Create Date: 2026-07-07

M5: ReviewDecision 新增 severity 字段——区分 critical/major/minor。
对标 compose/skills/review.md 的 🔴critical/🟡major/🟢minor 体系。
"""

revision = "20260707_severity"
down_revision = None  # 设置为上一个 migration 的 revision
depends_on = None


def upgrade():
    """添加 severity 列——默认为 'major'。"""
    op = __import__("alembic").op
    op.add_column(
        "review_decisions",
        __import__("sqlalchemy").Column(
            "severity",
            __import__("sqlalchemy").String(20),
            nullable=False,
            server_default="major",
        ),
    )


def downgrade():
    """回滚——删除 severity 列。"""
    op = __import__("alembic").op
    op.drop_column("review_decisions", "severity")
