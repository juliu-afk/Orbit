"""Integration tests: Compose + Dream + Compliance misc routes.

Small routes that are easy to cover with minimal mock setup.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mocks ─────────────────────────────────────────────────────────


class MockDreamEngine:
    _config = None

    async def run(self, config=None):
        from orbit.dream.models import DreamResult, DreamStatus

        return DreamResult(status=DreamStatus.COMPLETE, notes=["ok"])


class MockComposeOrchestrator:
    async def run_spec(self, spec: str) -> dict:
        return {"steps": 3, "status": "completed"}


class MockFileService:
    """Mock FileService for compliance /check endpoint."""

    async def read_file(self, file: str) -> str:
        # Return a file with float usage + router decorator — triggers multiple rules
        return "float x = 3.14\n@router.get('/test')\ndef handler(): pass\n"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def app():
    from orbit.api.main import create_app
    import importlib

    app = create_app(enable_auth=False, routes=["dream", "compose", "compliance_routes"])
    app.state.dream_engine = MockDreamEngine()
    app.state.compose_orchestrator = MockComposeOrchestrator()

    # Inject file service for compliance_routes
    comp = importlib.import_module("orbit.api.routes.compliance_routes")
    comp.set_file_service(MockFileService())

    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Dream tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dream_status(client):
    """GET /api/v1/dream/status → 200。"""
    resp = await client.get("/api/v1/dream/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "ready"


@pytest.mark.asyncio
async def test_dream_run(client):
    """POST /api/v1/dream/run → 200。"""
    resp = await client.post("/api/v1/dream/run", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_dream_status_no_engine():
    """GET /api/v1/dream/status DreamEngine 未配置 → not_configured。"""
    from orbit.api.main import create_app

    app = create_app(enable_auth=False, routes=["dream"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/dream/status")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_dream_run_no_engine():
    """POST /api/v1/dream/run DreamEngine 未配置 → 500。"""
    from orbit.api.main import create_app

    app = create_app(enable_auth=False, routes=["dream"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/dream/run", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == 500


# ── Compose tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_run(client):
    """POST /api/v1/compose/run → 200。"""
    resp = await client.post(
        "/api/v1/compose/run",
        json={"spec": "agents:\n  - name: test\n    role: developer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "steps" in data["data"]


@pytest.mark.asyncio
async def test_compose_run_no_orchestrator():
    """POST /api/v1/compose/run 未配置 → 500。"""
    from orbit.api.main import create_app

    app = create_app(enable_auth=False, routes=["compose"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/compose/run",
            json={"spec": "agents: []"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 500


# ── Compliance tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compliance_checklist_core(client):
    """GET /api/v1/compliance/checklist?task_type=core → 核心审查项。"""
    resp = await client.get("/api/v1/compliance/checklist?task_type=core")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("借贷平衡" in str(i) for i in items)


@pytest.mark.asyncio
async def test_compliance_checklist_frontend(client):
    """GET /api/v1/compliance/checklist?task_type=frontend → 前端审查项。"""
    resp = await client.get("/api/v1/compliance/checklist?task_type=frontend")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("TypeScript" in str(i) for i in items)


@pytest.mark.asyncio
async def test_compliance_checklist_default(client):
    """GET /api/v1/compliance/checklist 无参数 → 默认返回 core 审查项。"""
    resp = await client.get("/api/v1/compliance/checklist")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("debit == credit" in str(i) for i in items)  # core 默认项


@pytest.mark.asyncio
async def test_compliance_check_violations(client):
    """GET /api/v1/compliance/check?file=test.py → 扫描违规。"""
    resp = await client.get("/api/v1/compliance/check?file=test.py")
    assert resp.status_code == 200
    data = resp.json()
    assert "violations" in data
    has_float_rule = any(v["rule"] == "float-instead-of-decimal" for v in data["violations"])
    has_router_rule = any(v["rule"] == "router-endpoint" for v in data["violations"])
    assert has_float_rule or has_router_rule


@pytest.mark.asyncio
async def test_compliance_check_no_service():
    """GET /api/v1/compliance/check 无 file_service → 503。"""
    from orbit.api.main import create_app
    import importlib

    comp = importlib.import_module("orbit.api.routes.compliance_routes")
    comp.set_file_service(None)  # 重置模块全局——前面的测试可能已经注入

    app = create_app(enable_auth=False, routes=["compliance_routes"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/compliance/check?file=test.py")
        assert resp.status_code == 503
