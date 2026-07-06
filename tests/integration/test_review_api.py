"""Integration tests: Review API routes.

Covers review.py (6 endpoints, was 57%). Uses mock ReviewService injected
via set_review_service() — no DB needed.

Routes are at /api/v1/review/* (API_V1_STR prefix + router prefix).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mock Review domain objects ────────────────────────────────────


class _FakeReview:
    def __init__(self, id: str, task_id: str, status="pending", created_by="user"):
        self.id = id
        self.task_id = task_id
        self.status = status
        self.created_by = created_by
        now = datetime.now(tz=UTC)
        self.created_at = now
        self.updated_at = now


class _FakeDecision:
    def __init__(self, id: str):
        self.id = id


class _FakeComment:
    def __init__(self, id: str):
        self.id = id


class MockReviewService:
    """In-memory ReviewService — no DB, no SQLAlchemy."""

    def __init__(self):
        self.reviews: dict[str, _FakeReview] = {}
        self.decisions: dict[str, list[_FakeDecision]] = {}
        self.comments: dict[str, list[_FakeComment]] = {}

    async def create_review(self, task_id: str, created_by: str) -> _FakeReview:
        # Simulate conflict check — any existing review with same task_id
        for r in self.reviews.values():
            if r.task_id == task_id and r.status in (
                "pending", "in_review", "changes_requested",
            ):
                raise ValueError(f"Task {task_id} has active review")
        rid = str(uuid.uuid4())
        r = _FakeReview(rid, task_id, created_by=created_by)
        self.reviews[rid] = r
        return r

    async def get_review(self, review_id: str) -> _FakeReview | None:
        return self.reviews.get(review_id)

    async def record_decision(
        self, review_id, file_path, hunk_index, decision, decided_by, comment=None,
    ) -> _FakeDecision:
        if review_id not in self.reviews:
            raise ValueError(f"Review {review_id} not found")
        d = _FakeDecision(str(uuid.uuid4()))
        self.decisions.setdefault(review_id, []).append(d)
        r = self.reviews[review_id]
        if r.status == "pending":
            r.status = "in_review"
        return d

    async def add_comment(
        self, review_id, file_path, line_start, line_end, body, created_by,
    ) -> _FakeComment:
        if review_id not in self.reviews:
            raise ValueError(f"Review {review_id} not found")
        c = _FakeComment(str(uuid.uuid4()))
        self.comments.setdefault(review_id, []).append(c)
        return c

    async def transition_status(self, review_id: str, new_status: str) -> _FakeReview:
        VALID = {
            "pending": {"in_review"},
            "in_review": {"changes_requested", "approved"},
            "changes_requested": {"in_review"},
            "approved": {"merged"},
        }
        r = self.reviews.get(review_id)
        if not r:
            raise ValueError(f"Review {review_id} not found")
        if new_status not in VALID.get(r.status, set()):
            raise ValueError(f"Invalid transition: {r.status} -> {new_status}")
        r.status = new_status
        r.updated_at = datetime.now(tz=UTC)
        return r

    async def get_summary(self, review_id: str) -> dict:
        return {"total_files": 1, "files": {}, "total_decisions": 0}


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_svc():
    return MockReviewService()


@pytest.fixture
def app(mock_svc):
    from orbit.api.main import create_app
    from orbit.api.routes import review as review_mod

    review_mod.set_review_service(mock_svc)
    return create_app(enable_auth=False, routes=["review"])


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_review_success(client, mock_svc):
    """POST /review/sessions → 200 + review_id."""
    resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "review_id" in data
    assert data["status"] == "pending"
    assert data["created_by"] == "tester"


@pytest.mark.asyncio
async def test_create_review_conflict(client, mock_svc):
    """POST /review/sessions 同 task_id 活跃审查 → 409。"""
    task_id = str(uuid.uuid4())
    await client.post(
        "/api/v1/review/sessions",
        json={"task_id": task_id, "created_by": "tester"},
    )
    resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": task_id, "created_by": "tester2"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_review_found(client, mock_svc):
    """GET /review/sessions/{id} → 200。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.get(f"/api/v1/review/sessions/{rid}")
    assert resp.status_code == 200
    assert resp.json()["review_id"] == rid


@pytest.mark.asyncio
async def test_get_review_not_found(client):
    """GET /review/sessions/nonexistent → 404。"""
    resp = await client.get("/api/v1/review/sessions/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_record_decision_success(client, mock_svc):
    """POST /review/sessions/{id}/decisions → 200。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/decisions",
        json={
            "file_path": "src/main.py",
            "hunk_index": 0,
            "decision": "approved",
            "decided_by": "tester",
        },
    )
    assert resp.status_code == 200
    assert "decision_id" in resp.json()


@pytest.mark.asyncio
async def test_record_decision_invalid(client, mock_svc):
    """POST /review/sessions/{id}/decisions 非法 decision → 422。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/decisions",
        json={
            "file_path": "src/main.py",
            "hunk_index": 0,
            "decision": "INVALID_DECISION",
            "decided_by": "tester",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_record_decision_not_found_review(client):
    """POST /review/sessions/{id}/decisions 不存在的 review → 400。"""
    resp = await client.post(
        "/api/v1/review/sessions/nonexistent/decisions",
        json={
            "file_path": "src/main.py",
            "hunk_index": 0,
            "decision": "approved",
            "decided_by": "tester",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_comment_success(client, mock_svc):
    """POST /review/sessions/{id}/comments → 200。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/comments",
        json={
            "file_path": "src/main.py",
            "line_start": 10,
            "line_end": 15,
            "body": "这个逻辑可以简化",
            "created_by": "reviewer",
        },
    )
    assert resp.status_code == 200
    assert "comment_id" in resp.json()


@pytest.mark.asyncio
async def test_add_comment_not_found_review(client):
    """POST /review/sessions/{id}/comments 不存在的 review → 400。"""
    resp = await client.post(
        "/api/v1/review/sessions/nonexistent/comments",
        json={
            "file_path": "src/main.py",
            "line_start": 1,
            "line_end": 2,
            "body": "test",
            "created_by": "tester",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_transition_status_valid(client, mock_svc):
    """POST /review/sessions/{id}/status — pending→in_review。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/status",
        json={"status": "in_review"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"


@pytest.mark.asyncio
async def test_transition_status_invalid(client, mock_svc):
    """POST /review/sessions/{id}/status — pending→approved (非法跳转)。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/status",
        json={"status": "merged"},  # 不能从 pending 直接 merged
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_summary(client, mock_svc):
    """GET /review/sessions/{id}/summary → 200。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.get(f"/api/v1/review/sessions/{rid}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_files" in data
    assert "total_decisions" in data


@pytest.mark.asyncio
async def test_create_review_validation_fails(client):
    """POST /review/sessions 缺 task_id → 422。"""
    resp = await client.post(
        "/api/v1/review/sessions",
        json={"created_by": "tester"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transition_status_bad_input(client, mock_svc):
    """POST /review/sessions/{id}/status 非法 status 值 → 422。"""
    create_resp = await client.post(
        "/api/v1/review/sessions",
        json={"task_id": str(uuid.uuid4()), "created_by": "tester"},
    )
    rid = create_resp.json()["review_id"]

    resp = await client.post(
        f"/api/v1/review/sessions/{rid}/status",
        json={"status": "invalid_status"},
    )
    assert resp.status_code == 422
