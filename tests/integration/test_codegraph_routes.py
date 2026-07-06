"""Integration tests: CodeGraph API routes (5 GET endpoints, was 32%, 87 stmts).

Also exercises TestGapDetector via /test-gaps endpoint (indirect coverage bonus).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mocks ─────────────────────────────────────────────────────────


class MockCodeGraph:
    """Mock code_graph with all methods used by codegraph_routes."""

    async def find_definitions_with_positions(self, symbol: str) -> list[dict]:
        return [
            {
                "file_path": "src/main.py",
                "start_line": 10,
                "end_line": 15,
                "name": symbol,
                "kind": "function",
            }
        ]

    async def get_callers(self, symbol: str) -> list[str]:
        return ["caller_a", "caller_b"]

    async def get_symbol_meta(self, symbol: str) -> dict | None:
        return {"type": "int", "doc": "returns the count"}

    async def exists(self, symbol: str) -> bool:
        return True

    async def get_function_info(self, function_name: str) -> dict | None:
        return {"parameters": {"amount": "int", "label": "str"}}

    async def find_tests_for(self, function_name: str) -> list[dict]:
        return [{"params": {"amount": 100, "label": "test"}}]


class MockFileService:
    """Minimal FileService for /outline endpoint."""

    async def read_file(self, path: str) -> str:
        return "def hello():\n    pass\n\nclass Foo:\n    def bar(self):\n        pass\n"

    def detect_language(self, path: str) -> str:
        return "python"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def app():
    from orbit.api.main import create_app
    import importlib

    cg = importlib.import_module("orbit.api.routes.codegraph_routes")
    cg.set_code_graph(MockCodeGraph())
    cg.set_file_service(MockFileService())

    return create_app(enable_auth=False, routes=["codegraph_routes"])


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_go_to_definition(client):
    """GET /api/v1/codegraph/definition?symbol=foo → 200。"""
    resp = await client.get("/api/v1/codegraph/definition?symbol=my_func")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my_func"
    assert data["kind"] == "function"


@pytest.mark.asyncio
async def test_go_to_definition_not_found(client):
    """GET /api/v1/codegraph/definition?symbol=nonexistent → 200 (null result)。"""

    class NotFoundCG(MockCodeGraph):
        async def find_definitions_with_positions(self, symbol):
            return []

    import importlib

    cg = importlib.import_module("orbit.api.routes.codegraph_routes")
    cg.set_code_graph(NotFoundCG())
    resp = await client.get("/api/v1/codegraph/definition?symbol=nonexistent")
    assert resp.status_code == 200
    assert resp.json()["kind"] == "unknown"


@pytest.mark.asyncio
async def test_find_references(client):
    """GET /api/v1/codegraph/references?symbol=foo → 200。"""
    resp = await client.get("/api/v1/codegraph/references?symbol=my_func")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_outline(client):
    """GET /api/v1/codegraph/outline?file=test.py → 200——返回 AST 解析结果。"""
    resp = await client.get("/api/v1/codegraph/outline?file=test.py")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    names = {n["name"] for n in data}
    assert "hello" in names
    assert "Foo" in names


@pytest.mark.asyncio
async def test_hover_info(client):
    """GET /api/v1/codegraph/hover?symbol=foo → 200——返回类型+文档。"""
    resp = await client.get("/api/v1/codegraph/hover?symbol=my_func")
    assert resp.status_code == 200
    text = resp.json()
    assert "my_func" in text
    assert "int" in text


@pytest.mark.asyncio
async def test_hover_no_codegraph():
    """GET /api/v1/codegraph/hover codegraph 未配置 → None。"""
    from orbit.api.main import create_app
    import importlib

    cg = importlib.import_module("orbit.api.routes.codegraph_routes")
    cg.set_code_graph(None)
    app = create_app(enable_auth=False, routes=["codegraph_routes"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/codegraph/hover?symbol=foo")
        assert resp.status_code == 200
        assert resp.json() is None


@pytest.mark.asyncio
async def test_test_gaps(client):
    """GET /api/v1/codegraph/test-gaps?function=foo → 200——返回覆盖空洞。"""
    resp = await client.get("/api/v1/codegraph/test-gaps?function=calculate_tax")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "gaps" in data["data"]


@pytest.mark.asyncio
async def test_test_gaps_no_codegraph():
    """GET /api/v1/codegraph/test-gaps codegraph 未配置 → 返回提示。"""
    from orbit.api.main import create_app
    import importlib

    cg = importlib.import_module("orbit.api.routes.codegraph_routes")
    cg.set_code_graph(None)
    app = create_app(enable_auth=False, routes=["codegraph_routes"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/codegraph/test-gaps?function=test")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
