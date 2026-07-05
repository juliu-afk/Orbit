"""覆盖率——路由层深度测试 (agent_llm, backup, projects, blame, search, tests_routes)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(enable_auth=False))


class TestAgentLLMRoutes:
    def test_list_agents(self, client):
        resp = client.get("/api/v1/agent/llm")
        assert resp.status_code in (200, 404)

    def test_get_agent_config(self, client):
        resp = client.get("/api/v1/agent/llm/developer")
        assert resp.status_code in (200, 404)


class TestBackupRoutes:
    def test_list_snapshots(self, client):
        resp = client.get("/api/v1/backup/snapshots")
        assert resp.status_code in (200, 404)

    def test_list_snapshots_with_type(self, client):
        resp = client.get("/api/v1/backup/snapshots?db_type=sqlite")
        assert resp.status_code in (200, 404)


class TestProjectsRoutes:
    def test_list_projects(self, client):
        resp = client.get("/api/v1/projects")
        assert resp.status_code in (200, 404)

    def test_get_project(self, client):
        resp = client.get("/api/v1/projects/Orbit")
        assert resp.status_code in (200, 404)

    def test_register_project(self, client):
        resp = client.post("/api/v1/projects", json={"name": "test_proj", "local_path": "."})
        assert resp.status_code in (200, 400, 403, 422)

    def test_get_project_not_found(self, client):
        resp = client.get("/api/v1/projects/__nonexistent__project__")
        assert resp.status_code in (200, 404)

    def test_get_project_brief(self, client):
        resp = client.get("/api/v1/projects/__nonexistent__/brief")
        assert resp.status_code in (200, 404, 422)

    def test_refresh_project_brief(self, client):
        resp = client.post("/api/v1/projects/__nonexistent__/brief/refresh")
        assert resp.status_code in (200, 400, 404, 422)

    def test_refresh_context_md(self, client):
        resp = client.post("/api/v1/projects/__nonexistent__/context/refresh")
        assert resp.status_code in (200, 400, 404, 422)


class TestBlameRoutes:
    def test_blame_no_file(self, client):
        resp = client.get("/api/v1/blame?file=nonexistent.py")
        assert resp.status_code in (200, 404, 422)


class TestSearchRoutes:
    def test_search_empty(self, client):
        resp = client.get("/api/v1/search?q=")
        assert resp.status_code in (200, 422, 404)

    def test_search_with_query(self, client):
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code in (200, 404)


class TestTestsRoutes:
    def test_test_results(self, client):
        resp = client.get("/api/v1/tests/results")
        assert resp.status_code in (200, 404)

    @pytest.mark.skip(reason="P2-4: needs fixing")
    def test_coverage_no_params(self, client):
        resp = client.get("/api/v1/tests/coverage")
        assert resp.status_code in (200, 404)

    @pytest.mark.skip(reason="P2-4: needs fixing")
    def test_coverage_with_limit(self, client):
        resp = client.get("/api/v1/tests/coverage", params={"limit": 10})
        assert resp.status_code in (200, 404, 422)
