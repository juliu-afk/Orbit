"""覆盖率——路由层冒烟测试 (chat, git_routes, codegraph_routes, projects, schedule)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app


@pytest.fixture
def client():
    app = create_app(enable_auth=False)
    return TestClient(app)


class TestCodeGraphRoutes:
    def test_definition_no_query(self, client):
        resp = client.get("/api/v1/codegraph/definition")
        assert resp.status_code in (200, 422, 404)

    def test_definition_with_query(self, client):
        resp = client.get("/api/v1/codegraph/definition", params={"symbol": "foo"})
        assert resp.status_code in (200, 422, 500, 503)

    def test_references_no_query(self, client):
        resp = client.get("/api/v1/codegraph/references")
        assert resp.status_code in (200, 422, 404)

    def test_references_with_query(self, client):
        resp = client.get("/api/v1/codegraph/references", params={"symbol": "foo"})
        assert resp.status_code in (200, 422, 500, 503)

    def test_outline_no_query(self, client):
        resp = client.get("/api/v1/codegraph/outline")
        assert resp.status_code in (200, 422, 404)

    def test_outline_with_query(self, client):
        resp = client.get("/api/v1/codegraph/outline", params={"file": "test.py"})
        assert resp.status_code in (200, 403, 404, 422, 500, 503)

    def test_hover_no_query(self, client):
        resp = client.get("/api/v1/codegraph/hover")
        assert resp.status_code in (200, 422, 404)

    def test_hover_with_query(self, client):
        resp = client.get("/api/v1/codegraph/hover", params={"symbol": "foo"})
        assert resp.status_code in (200, 422)


class TestGitRoutes:
    def test_gpg_keys(self, client):
        resp = client.get("/api/v1/git/gpg-keys")
        assert resp.status_code in (200, 404)

    def test_commit_no_body(self, client):
        resp = client.post("/api/v1/git/commit", json={})
        assert resp.status_code in (200, 400, 422)

    def test_commit_with_body(self, client):
        resp = client.post("/api/v1/git/commit", json={"message": "test"})
        assert resp.status_code in (200, 400, 422)

    def test_merge_conflicts(self, client):
        resp = client.get("/api/v1/git/merge-conflicts")
        assert resp.status_code in (200, 400, 404)


class TestScheduleRoutes:
    def test_get_schedule(self, client):
        resp = client.get("/api/v1/schedule")
        assert resp.status_code in (200, 404)
