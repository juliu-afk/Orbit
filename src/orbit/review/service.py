"""审查引擎业务逻辑。

WHY 独立 service 层：路由层只做校验+格式化，
业务逻辑（状态机转换、决策聚合）在 service。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orbit.review.models import Review, ReviewBase, ReviewComment, ReviewDecision


class ReviewService:
    """审查引擎——审查会话的 CRUD + 状态机。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def init_db(self) -> None:
        """创建所有审查模块表（首次启动调用）。"""
        async with self.session_factory() as session:
            async with session.begin():
                # WHY run_sync：create_all 是同步方法，async engine 需要 run_sync 包装
                await session.run_sync(ReviewBase.metadata.create_all)

    async def create_review(self, task_id: str, created_by: str) -> Review:
        """创建审查会话。

        Raises ValueError if task 已有活跃审查。
        """
        async with self.session_factory() as session:
            existing = await session.execute(
                select(Review).where(
                    Review.task_id == task_id,
                    Review.status.in_(["pending", "in_review", "changes_requested"]),
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Task {task_id} 已有活跃审查会话")
            review = Review(task_id=task_id, created_by=created_by, status="pending")
            session.add(review)
            await session.commit()
            await session.refresh(review)
            return review

    async def get_review(self, review_id: str) -> Review | None:
        """获取审查会话。"""
        async with self.session_factory() as session:
            return await session.get(Review, review_id)

    async def get_review_by_task(self, task_id: str) -> Review | None:
        """按 task_id 查找审查会话。"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Review).where(Review.task_id == task_id)
            )
            return result.scalar_one_or_none()

    async def record_decision(
        self,
        review_id: str,
        file_path: str,
        hunk_index: int,
        decision: str,
        decided_by: str,
        comment: str | None = None,
    ) -> ReviewDecision:
        """记录审查决定（批准/打回/注释）。

        自动更新审查状态为 in_review（首次决定时）。
        """
        async with self.session_factory() as session:
            rd = ReviewDecision(
                review_id=review_id,
                file_path=file_path,
                hunk_index=hunk_index,
                decision=decision,
                decided_by=decided_by,
                comment=comment,
            )
            session.add(rd)
            review = await session.get(Review, review_id)
            if review and review.status == "pending":
                review.status = "in_review"
            await session.commit()
            return rd

    async def add_comment(
        self,
        review_id: str,
        file_path: str,
        line_start: int,
        line_end: int,
        body: str,
        created_by: str,
    ) -> ReviewComment:
        """添加审查注释。"""
        async with self.session_factory() as session:
            comment = ReviewComment(
                review_id=review_id,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                body=body,
                created_by=created_by,
            )
            session.add(comment)
            await session.commit()
            return comment

    async def transition_status(self, review_id: str, new_status: str) -> Review:
        """审查状态流转。

        合法转换：
        - pending → in_review（首次打开审查页）
        - in_review → changes_requested（打回 Agent）
        - in_review → approved（全部 hunk 批准 + 无未解决注释）
        - approved → merged（Git commit 成功）
        - changes_requested → in_review（Agent 修复后重新审查）
        """
        VALID_TRANSITIONS = {
            "pending": {"in_review"},
            "in_review": {"changes_requested", "approved"},
            "changes_requested": {"in_review"},
            "approved": {"merged"},
        }
        async with self.session_factory() as session:
            review = await session.get(Review, review_id)
            if not review:
                raise ValueError(f"审查会话 {review_id} 不存在")
            allowed = VALID_TRANSITIONS.get(review.status, set())
            if new_status not in allowed:
                raise ValueError(
                    f"状态转换非法: {review.status} → {new_status}。"
                    f"允许: {allowed}"
                )
            review.status = new_status
            review.updated_at = datetime.utcnow()
            await session.commit()
            return review

    async def get_summary(self, review_id: str) -> dict:
        """获取审查摘要——各文件的批准/打回/待审统计。"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ReviewDecision).where(ReviewDecision.review_id == review_id)
            )
            decisions = result.scalars().all()
            by_file: dict[str, dict[str, int]] = {}
            for d in decisions:
                if d.file_path not in by_file:
                    by_file[d.file_path] = {"approved": 0, "rejected": 0, "comment": 0}
                by_file[d.file_path][d.decision] += 1
            return {
                "total_files": len(by_file),
                "files": by_file,
                "total_decisions": len(decisions),
            }
