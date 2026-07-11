"""Integration tests: Insights + Search + Tests API routes.

Covers:
- insights_routes.py (3 GET, was 38%) — mock review_service + code_graph
- search_routes.py (1 GET, was 39%) — temp workspace with test files
- tests_routes.py (2 GET, was 44%) — temp workspace + fake coverage.json
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mock helpers ──────────────────────────────────────────────────


class MockReviewService:
    async def get_summary(self, task_id: str) -> dict:
        return {"files": {"src/a.py": {"approved": 1, "rejected": 3}}, "total_decisions": 4}


class MockCodeGraph:
    async def get_callers(self, symbol: str) -> list[str]:
        return ["src/caller_a.py", "src/caller_b.py"]


class MockPytestProcess:
    """Mock asyncio subprocess for tests_routes."""
    returncode = 0

    async def communicate(self):
        return b"", b""


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_review_svc():
    return MockReviewService()


@pytest.fixture
def mock_code_graph():
    return MockCodeGraph()


@pytest.fixture
def workspace_dir():
    """Temporary workspace on D: drive (same as repo) to avoid cross-drive path errors on Windows."""
    # WHY D: drive: ntpath.relpath fails on cross-drive C:→D:
    base = os.environ.get("TEMP", tempfile.gettempdir())
    # Ensure same drive as the project
    project_drive = os.path.splitdrive(os.getcwd())[0]
    if os.path.splitdrive(base)[0] != project_drive:
        base = os.path.join(project_drive + os.sep, "Temp")
        os.makedirs(base, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as d:
        # Create test files for filename search
        (Path(d) / "src").mkdir(parents=True, exist_ok=True)
        (Path(d) / "src" / "main.py").write_text("print('hello')")
        (Path(d) / "src" / "utils.py").write_text("def helper(): pass")
        (Path(d) / "tests").mkdir(exist_ok=True)
        (Path(d) / "tests" / "test_main.py").write_text("def test(): pass")
        # Fake coverage.json
        coverage_data = {
            "totals": {
                "covered_lines": 100,
                "num_statements": 150,
                "percent_covered": 66.67,
                "missing_lines": 50,
            },
            "files": {
                "src/main.py": {
                    "summary": {
                        "covered_lines": 80, "num_statements": 100,
                        "percent_covered": 80.0,
                        "missing_lines": [10, 20, 30, 40, 50,
                                          60, 70, 80, 90, 100,
                                          110, 120, 130, 140, 150,
                                          160, 170, 180, 190, 200],
                    },
                }
            },
        }
        with open(Path(d) / "coverage.json", "w") as f:
            json.dump(coverage_data, f)
        yield d


@pytest.fixture
def app(workspace_dir, mock_review_svc, mock_code_graph):
    from orbit.api.main import create_app
    from orbit.api.routes import _workspace as ws_mod

    ws_mod.set_workspace(workspace_dir)

    # Inject mocks for insights
    import importlib

    insights = importlib.import_module("orbit.api.routes.insights_routes")
    insights.set_review_service(mock_review_svc)
    insights.set_code_graph(mock_code_graph)

    return create_app(enable_auth=False, routes=["insights_routes", "search_routes", "tests_routes"])


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Insights tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insights_risk_scores(client):
    """GET /api/v1/insights/risk?task_id=test → 200 + risk scores."""
    resp = await client.get("/api/v1/insights/risk?task_id=test-task-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file"] == "src/a.py"
    assert data[0]["score"] == 75  # 3 rejected / 4 total = 75%
    assert data[0]["level"] == "high"


@pytest.mark.asyncio
async def test_insights_impact_analysis(client):
    """GET /api/v1/insights/impact?symbol=foo → 200 + impact nodes."""
    resp = await client.get("/api/v1/insights/impact?symbol=my_function")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["level"] == "direct"


# ── Search tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_empty_query(client):
    """GET /api/v1/search?q= → 422——query 必填。"""
    resp = await client.get("/api/v1/search?q=")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_by_filename(client):
    """GET /api/v1/search?q=main&search_type=file → 找到 main.py。"""
    resp = await client.get("/api/v1/search?q=main&search_type=file")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    filenames = [r["file"] for r in data]
    assert any("main.py" in f for f in filenames)


# ── Tests routes tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tests_coverage(client):
    """GET /api/v1/tests/coverage → 200——读取 coverage.json, 返回 list[CoverageFile]."""
    resp = await client.get("/api/v1/tests/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["pct"] == 80.0  # From our fake coverage.json
