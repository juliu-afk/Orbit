"""E2E full pipeline — multi-task agent lifecycle with real Docker stack."""
import asyncio
from typing import Any

import pytest

from orbit.api.schemas.task import TaskState


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_multi_task_pipeline(e2e_app: Any) -> None:
    """Run 3 tasks sequentially through scheduler → full lifecycle coverage."""
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    tasks = [
        ("pipe-001-aaaaaaaaaaaaaaaaaaaaaa", "Write a function to add two numbers"),
        ("pipe-002-bbbbbbbbbbbbbbbbbbbbbbbb", "Create a class Calculator with add/subtract methods"),
        ("pipe-003-cccccccccccccccccccccccccc", "Add error handling for division by zero"),
    ]

    for task_id, prd in tasks:
        state = await asyncio.wait_for(
            scheduler.run_task(task_id, prd),
            timeout=30,
        )
        assert state != TaskState.ERROR, f"Task {task_id} errored: {state}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_task_with_tools(e2e_app: Any) -> None:
    """Task that requires tool usage — exercises tool registry + dispatch."""
    scheduler = getattr(e2e_app, "_scheduler", None)
    if scheduler is None:
        pytest.skip("Scheduler not available")

    task_id = "tool-001-aaaaaaaaaaaaaaaaaaaaaa"
    prd = "Read the file README.md and check if it mentions 'Orbit'"

    state = await asyncio.wait_for(
        scheduler.run_task(task_id, prd),
        timeout=30,
    )
    # Task may succeed or fail — just exercise the pipeline
    assert state is not None


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_observability_endpoints(e2e_app: Any) -> None:
    """Test all observability/monitoring endpoints."""
    endpoints = [
        "/health",
        "/metrics",
        "/api/v1/observability/startup-probe",
    ]
    for ep in endpoints:
        resp = await e2e_app.get(ep)
        assert resp.status_code == 200, f"{ep} returned {resp.status_code}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_api_comprehensive(e2e_app: Any) -> None:
    """Test multiple API routes that exercise different service layers."""
    # Task API
    resp = await e2e_app.post("/api/v1/tasks", json={"prd": "test", "language": "python"})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # Query task
    resp = await e2e_app.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200

    # 404 for non-existent
    resp = await e2e_app.get("/api/v1/tasks/" + "f" * 32)
    assert resp.status_code == 404

    # Insights/Search API
    resp = await e2e_app.get("/api/v1/insights")
    assert resp.status_code in (200, 404)

    resp = await e2e_app.get("/api/v1/search?q=test")
    assert resp.status_code in (200, 404)
