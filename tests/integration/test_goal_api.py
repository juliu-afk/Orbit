"""Goal+Loop API integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class MockOrchestrator:
    """Mock orchestrator — doesn't actually run agents."""

    def __init__(self):
        class Mem:
            goal_description = ""
            sub_tasks = {}

        self.memory = Mem()

    async def run(self, goal):
        pass


class MockScheduler:
    async def create(self, interval, command):
        from orbit.loop.models import LoopSchedule

        return LoopSchedule(interval_seconds=300, command=command)

    async def start(self, lid):
        pass

    async def stop(self, lid):
        pass

    async def pause(self, lid):
        pass

    async def resume(self, lid):
        pass

    def list_all(self):
        return []


@pytest.fixture
def client():
    from orbit.api.main import app

    app.state.meta_orchestrator = MockOrchestrator()
    app.state.loop_scheduler = MockScheduler()
    return TestClient(app)


class TestGoalAPI:
    def test_create_goal(self, client):
        resp = client.post("/api/v1/goal", json={"description": "test"})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_get_status(self, client):
        resp = client.get("/api/v1/goal")
        assert resp.status_code == 200

    def test_cancel(self, client):
        resp = client.delete("/api/v1/goal")
        assert resp.status_code == 200


class TestLoopAPI:
    def test_create_loop(self, client):
        resp = client.post("/api/v1/loop", json={"interval": "5m", "command": "/goal test"})
        assert resp.status_code == 200

    def test_list(self, client):
        resp = client.get("/api/v1/loop")
        assert resp.status_code == 200

    def test_stop(self, client):
        resp = client.delete("/api/v1/loop/any")
        assert resp.status_code == 200
