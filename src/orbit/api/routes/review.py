"""审查 API 路由 (Step 9 Phase 1)."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from orbit.review.service import ReviewService

router = APIRouter(prefix="/review", tags=["review"])
_review_service: ReviewService | None = None


def set_review_service(svc: ReviewService) -> None:
    global _review_service
    _review_service = svc


def _svc() -> ReviewService:
    if _review_service is None:
        raise RuntimeError("ReviewService not initialized")
    return _review_service


class CreateReviewRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=36)
    created_by: str = Field("user", max_length=100)


class ReviewResponse(BaseModel):
    review_id: str
    task_id: str
    status: str
    created_by: str
    created_at: float
    updated_at: float


class RecordDecisionRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=500)
    hunk_index: int = Field(..., ge=0)
    decision: str = Field(..., pattern=r"^(approved|rejected|comment)$")
    decided_by: str = Field("user", max_length=100)
    comment: str | None = Field(None, max_length=2000)


class AddCommentRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=500)
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)
    body: str = Field(..., min_length=1, max_length=2000)
    created_by: str = Field("user", max_length=100)


class TransitionStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(in_review|changes_requested|approved|merged)$")


class ReviewSummaryResponse(BaseModel):
    total_files: int
    files: dict[str, dict[str, int]]
    total_decisions: int


def _ts(dt) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@router.post("/sessions", response_model=ReviewResponse)
async def create_review(req: CreateReviewRequest):
    try:
        review = await _svc().create_review(req.task_id, req.created_by)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return ReviewResponse(
        review_id=review.id,
        task_id=review.task_id,
        status=review.status,
        created_by=review.created_by,
        created_at=_ts(review.created_at),
        updated_at=_ts(review.updated_at),
    )


@router.get("/sessions/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: str):
    review = await _svc().get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewResponse(
        review_id=review.id,
        task_id=review.task_id,
        status=review.status,
        created_by=review.created_by,
        created_at=_ts(review.created_at),
        updated_at=_ts(review.updated_at),
    )


@router.post("/sessions/{review_id}/decisions")
async def record_decision(review_id: str, req: RecordDecisionRequest):
    try:
        rd = await _svc().record_decision(
            review_id=review_id,
            file_path=req.file_path,
            hunk_index=req.hunk_index,
            decision=req.decision,
            decided_by=req.decided_by,
            comment=req.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"decision_id": rd.id}


@router.post("/sessions/{review_id}/comments")
async def add_comment(review_id: str, req: AddCommentRequest):
    try:
        c = await _svc().add_comment(
            review_id=review_id,
            file_path=req.file_path,
            line_start=req.line_start,
            line_end=req.line_end,
            body=req.body,
            created_by=req.created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"comment_id": c.id}


@router.post("/sessions/{review_id}/status", response_model=ReviewResponse)
async def transition_status(review_id: str, req: TransitionStatusRequest):
    try:
        review = await _svc().transition_status(review_id, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ReviewResponse(
        review_id=review.id,
        task_id=review.task_id,
        status=review.status,
        created_by=review.created_by,
        created_at=_ts(review.created_at),
        updated_at=_ts(review.updated_at),
    )


@router.get("/sessions/{review_id}/summary", response_model=ReviewSummaryResponse)
async def get_summary(review_id: str):
    data = await _svc().get_summary(review_id)
    return ReviewSummaryResponse(**data)
