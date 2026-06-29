"""审查引擎业务逻辑。状态机转换+决策聚合。"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from orbit.review.models import Review, ReviewBase, ReviewComment, ReviewDecision

class ReviewService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def init_db(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.run_sync(ReviewBase.metadata.create_all)

    async def create_review(self, task_id: str, created_by: str) -> Review:
        async with self.session_factory() as session:
            existing = await session.execute(
                select(Review).where(Review.task_id == task_id,
                Review.status.in_(["pending","in_review","changes_requested"])))
            if existing.scalar_one_or_none():
                raise ValueError(f"Task {task_id} has active review")
            review = Review(task_id=task_id, created_by=created_by, status="pending")
            session.add(review); await session.commit(); await session.refresh(review)
            return review

    async def get_review(self, review_id: str) -> Review | None:
        async with self.session_factory() as session:
            return await session.get(Review, review_id)

    async def record_decision(self, review_id: str, file_path: str, hunk_index: int,
            decision: str, decided_by: str, comment: str | None = None) -> ReviewDecision:
        async with self.session_factory() as session:
            rd = ReviewDecision(review_id=review_id, file_path=file_path,
                hunk_index=hunk_index, decision=decision, decided_by=decided_by, comment=comment)
            session.add(rd)
            review = await session.get(Review, review_id)
            if review and review.status == "pending": review.status = "in_review"
            await session.commit()
            return rd

    async def add_comment(self, review_id: str, file_path: str, line_start: int,
            line_end: int, body: str, created_by: str) -> ReviewComment:
        async with self.session_factory() as session:
            c = ReviewComment(review_id=review_id, file_path=file_path,
                line_start=line_start, line_end=line_end, body=body, created_by=created_by)
            session.add(c); await session.commit()
            return c

    async def transition_status(self, review_id: str, new_status: str) -> Review:
        VALID = {"pending":{"in_review"},"in_review":{"changes_requested","approved"},
                 "changes_requested":{"in_review"},"approved":{"merged"}}
        async with self.session_factory() as session:
            review = await session.get(Review, review_id)
            if not review: raise ValueError(f"Review {review_id} not found")
            if new_status not in VALID.get(review.status, set()):
                raise ValueError(f"Invalid transition: {review.status} -> {new_status}")
            review.status = new_status
            review.updated_at = datetime.now(tz=timezone.utc)
            await session.commit()
            return review

    async def get_summary(self, review_id: str) -> dict:
        async with self.session_factory() as session:
            r = await session.execute(select(ReviewDecision).where(ReviewDecision.review_id == review_id))
            by_file = {}
            for d in r.scalars().all():
                if d.file_path not in by_file: by_file[d.file_path] = {"approved":0,"rejected":0,"comment":0}
                by_file[d.file_path][d.decision] += 1
            return {"total_files":len(by_file),"files":by_file,"total_decisions":sum(sum(f.values()) for f in by_file.values())}
