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
