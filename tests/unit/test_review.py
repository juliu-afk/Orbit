"""ReviewService 单元测试——状态机转换 + CRUD 操作。

transition_status 是核心状态机，纯逻辑。
create_review/get_review 用 in-memory SQLite + async sessionmaker。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orbit.review.models import Review, ReviewComment, ReviewDecision
from orbit.review.service import ReviewService


# ── in-memory SQLite fixture ──────────────────────────────

@pytest.fixture
async def svc():
    """创建使用 in-memory SQLite 的 ReviewService。

    WHY 手动建表: ReviewService.init_db() 使用 session.run_sync(create_all)
    传递方式与 SQLAlchemy async API 不兼容。通过 engine.begin() 直接建表绕过。
    """
    from orbit.review.models import ReviewBase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # 手动建表（async 兼容）
    async with engine.begin() as conn:
        await conn.run_sync(ReviewBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = ReviewService(factory)
    yield service
    await engine.dispose()


@pytest.fixture
async def review(svc: ReviewService):
    """预创建一个 Review。"""
    return await svc.create_review("task-001", "test-user")


# ── TransitionStatus 状态机 ───────────────────────────────

class TestTransitionStatus:
    """核心状态机——pending→in_review→approved/changes_requested→..."""

    @pytest.mark.asyncio
    async def test_pending_to_in_review(self, svc, review):
        r = await svc.transition_status(review.id, "in_review")
        assert r.status == "in_review"

    @pytest.mark.asyncio
    async def test_in_review_to_approved(self, svc, review):
        await svc.transition_status(review.id, "in_review")
        r = await svc.transition_status(review.id, "approved")
        assert r.status == "approved"

    @pytest.mark.asyncio
    async def test_in_review_to_changes_requested(self, svc, review):
        await svc.transition_status(review.id, "in_review")
        r = await svc.transition_status(review.id, "changes_requested")
        assert r.status == "changes_requested"

    @pytest.mark.asyncio
    async def test_changes_requested_to_in_review(self, svc, review):
        await svc.transition_status(review.id, "in_review")
        await svc.transition_status(review.id, "changes_requested")
        r = await svc.transition_status(review.id, "in_review")
        assert r.status == "in_review"

    @pytest.mark.asyncio
    async def test_approved_to_merged(self, svc, review):
        await svc.transition_status(review.id, "in_review")
        await svc.transition_status(review.id, "approved")
        r = await svc.transition_status(review.id, "merged")
        assert r.status == "merged"

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, svc, review):
        """pending→approved 是无效跳转。"""
        with pytest.raises(ValueError, match="Invalid transition"):
            await svc.transition_status(review.id, "approved")

    @pytest.mark.asyncio
    async def test_pending_to_changes_requested_invalid(self, svc, review):
        with pytest.raises(ValueError):
            await svc.transition_status(review.id, "changes_requested")

    @pytest.mark.asyncio
    async def test_approved_back_to_in_review_invalid(self, svc, review):
        await svc.transition_status(review.id, "in_review")
        await svc.transition_status(review.id, "approved")
        with pytest.raises(ValueError):
            await svc.transition_status(review.id, "in_review")

    @pytest.mark.asyncio
    async def test_merged_is_terminal(self, svc, review):
        """merged 后不能再 transition。"""
        await svc.transition_status(review.id, "in_review")
        await svc.transition_status(review.id, "approved")
        await svc.transition_status(review.id, "merged")
        with pytest.raises(ValueError):
            await svc.transition_status(review.id, "in_review")


# ── CRUD ─────────────────────────────────────────────────

class TestCreateReview:
    @pytest.mark.asyncio
    async def test_create_review_default_status(self, svc):
        r = await svc.create_review("task-002", "user-a")
        assert r.status == "pending"
        assert r.task_id == "task-002"
        assert r.created_by == "user-a"

    @pytest.mark.asyncio
    async def test_create_duplicate_active_review_rejected(self, svc):
        await svc.create_review("task-003", "user-a")
        # 第二个活跃审查应拒绝（同 task_id）
        with pytest.raises(ValueError, match="active"):
            await svc.create_review("task-003", "user-b")


class TestGetReview:
    @pytest.mark.asyncio
    async def test_get_existing_review(self, svc, review):
        r = await svc.get_review(review.id)
        assert r is not None
        assert r.id == review.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, svc):
        r = await svc.get_review("nonexistent-id")
        assert r is None


class TestRecordDecision:
    @pytest.mark.asyncio
    async def test_record_decision_updates_status(self, svc, review):
        """record_decision 自动将 pending→in_review。"""
        d = await svc.record_decision(
            review.id, "src/a.py", 1, "approved", "reviewer-1"
        )
        assert d.file_path == "src/a.py"
        assert d.decision == "approved"

        # 验证审查状态自动推进
        r = await svc.get_review(review.id)
        assert r.status == "in_review"

    @pytest.mark.asyncio
    async def test_record_decision_with_comment(self, svc, review):
        d = await svc.record_decision(
            review.id, "src/b.py", 2, "rejected", "reviewer-1",
            comment="Needs better variable names",
        )
        assert d.comment == "Needs better variable names"


class TestAddComment:
    @pytest.mark.asyncio
    async def test_add_comment(self, svc, review):
        c = await svc.add_comment(
            review.id, "src/x.py", 5, 10, "Fix this function", "reviewer-1",
        )
        assert c.file_path == "src/x.py"
        assert c.body == "Fix this function"
        assert c.status == "open"
        assert c.created_by == "reviewer-1"


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_empty_summary(self, svc, review):
        summary = await svc.get_summary(review.id)
        assert summary["total_decisions"] == 0
        assert summary["total_files"] == 0

    @pytest.mark.asyncio
    async def test_summary_with_decisions(self, svc, review):
        await svc.record_decision(review.id, "a.py", 1, "approved", "r1")
        await svc.record_decision(review.id, "a.py", 2, "rejected", "r1")
        await svc.record_decision(review.id, "b.py", 1, "comment", "r1")

        summary = await svc.get_summary(review.id)
        assert summary["total_decisions"] == 3
        assert summary["total_files"] == 2
        # files 是 dict: {path: {approved, rejected, comment}}
        assert summary["files"]["a.py"]["approved"] == 1
        assert summary["files"]["a.py"]["rejected"] == 1
        assert summary["files"]["b.py"]["comment"] == 1
