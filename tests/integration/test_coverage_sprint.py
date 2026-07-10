"""Integration tests for coverage sprint — multi-module chains.
Strategy B: each test exercises 5-10 modules at once.

Covers: task creation, tool registry, SSE streaming.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from orbit.api.dependencies import verify_stream_token

    app = FastAPI()
    app.dependency_overrides[verify_stream_token] = lambda: "test-token"

    mock_llm = AsyncMock()
    mock_llm.generate.return_value = MagicMock(content="ok", model="test")
    app.state.llm = mock_llm

    from orbit.tools.registry import ToolRegistry
    app.state.tools = ToolRegistry()

    from orbit.agents.factory import AgentFactory
    app.state.agent_factory = AgentFactory

    from orbit.stream.sse import router as sse_router
    app.include_router(sse_router)

    return TestClient(app)


# ── 1. Task lifecycle ─────────────────────────────────────


class TestTaskLifecycle:
    @pytest.fixture
    def client(self):
        return _make_client()

    def test_run_task(self, client):
        resp = client.post(
            "/api/v1/agent/dev/run",
            json={"task": "integration test", "role": "developer"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert "task_id" in resp.json()["data"]

    def test_stream_endpoint(self, client):
        run = client.post(
            "/api/v1/agent/dev/run",
            json={"task": "stream test", "role": "developer"},
        )
        task_id = run.json()["data"]["task_id"]
        resp = client.get(
            f"/api/v1/agent/dev/stream?task_id={task_id}&task=hello&token=orbit-local-stream",
        )
        assert resp.status_code == 200


# ── 2. Tool registry ──────────────────────────────────────


class TestToolRegistryIntegration:
    @pytest.fixture
    def registry(self):
        from orbit.tools.registry import ToolRegistry
        from orbit.tools.models import ToolSchema, ToolPermission

        reg = ToolRegistry()
        schema = ToolSchema(
            name="echo",
            version="1.0.0",
            description="Echo",
            parameters={"message": {"type": "string"}},
            permissions=[ToolPermission.READ],
        )

        async def handler(params):
            return f"echo: {params.get('message', '')}"

        reg.register(schema, handler)
        return reg

    def test_schema_retrieval(self, registry):
        s = registry.get_schema("echo")
        assert s.name == "echo"

    def test_list_tools(self, registry):
        tools = registry.list_tools()
        assert len(tools) > 0

    def test_get_latest_version(self, registry):
        """get_latest_version returns version string."""
        v = registry.get_latest_version("echo")
        assert v == "1.0.0"
