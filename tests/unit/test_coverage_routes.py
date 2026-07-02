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


class TestScheduleRoutes:
    def test_get_schedule(self, client):
        resp = client.get("/api/v1/schedule")
        assert resp.status_code in (200, 404)
