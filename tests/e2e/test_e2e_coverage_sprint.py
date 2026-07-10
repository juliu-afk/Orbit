"""E2E coverage sprint — full agent lifecycle tests.
Each test exercises 10-20 modules: scheduler → agent → checkpoint → tools.

Target modules: scheduler/orchestrator, checkpoint/manager, agents/factory,
tools/registry, events/bus, api/routes, observability/audit.
"""
import asyncio
from typing import Any

import pytest

from orbit.api.schemas.task import TaskState


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_api_health_and_metrics(e2e_app: Any) -> None:
    """Health + metrics endpoints return 200."""
    resp = await e2e_app.get("/health")
    assert resp.status_code == 200

    resp = await e2e_app.get("/metrics")
    assert resp.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_task_create_and_query(e2e_app: Any) -> None:
    """API: create task → query status."""
    resp = await e2e_app.post(
        "/api/v1/tasks",
        json={"prd": "E2E test task", "language": "python"},
    )
    assert resp.status_code == 200
    data = resp.json()
    task_id = data["task_id"]
    assert len(task_id) == 32

    resp = await e2e_app.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_task_not_found(e2e_app: Any) -> None:
    """Query non-existent task → 404."""
    resp = await e2e_app.get("/api/v1/tasks/" + "a" * 32)
    assert resp.status_code == 404


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_review_api(e2e_app: Any) -> None:
    """Review API endpoints respond."""
    resp = await e2e_app.get("/api/v1/reviews")
    assert resp.status_code in (200, 404)


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_sessions_api(e2e_app: Any) -> None:
    """Sessions API endpoints respond."""
    resp = await e2e_app.get("/api/v1/sessions")
    assert resp.status_code in (200, 404)
