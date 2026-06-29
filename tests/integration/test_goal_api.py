"""Goal+Loop API integration tests.

P1-5: 增强断言 + 错误路径覆盖。
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


class MockOrchestrator:
    """Mock orchestrator."""
    def __init__(self):
        class Mem:
            goal_description = ""
            sub_tasks: dict = {}
        self.memory = Mem()
    async def run(self, goal):
        pass


class MockScheduler:
    def __init__(self, expected_interval: int | None = None):
        self._expected = expected_interval
    async def create(self, interval, command):
        from orbit.loop.models import LoopSchedule
        # P1-5: 校验 interval 被正确解析
        seconds = 300
        if interval == "10m":
            seconds = 600
        elif interval == "1h":
            seconds = 3600
        return LoopSchedule(interval_seconds=seconds, command=command)
    async def start(self, lid): pass
    async def stop(self, lid): pass
    async def pause(self, lid): pass
    async def resume(self, lid): pass
    def list_all(self): return []


@pytest.fixture
def client():
    from orbit.api.main import app
    app.state.meta_orchestrator = MockOrchestrator()
    app.state.loop_scheduler = MockScheduler()
    return TestClient(app)


class TestGoalAPI:
    def test_create_goal_returns_valid_response(self, client):
        resp = client.post("/api/v1/goal", json={"description": "实现认证模块"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "active"
        assert data["data"]["goal_id"]  # 非空 UUID

    def test_create_goal_with_constraints(self, client):
        resp = client.post("/api/v1/goal", json={
            "description": "test",
            "constraints": ["不修改 tests/"],
            "verification_commands": ["pytest -q"],
            "total_budget": 500000,
            "max_parallel_tasks": 3,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_get_status_returns_fields(self, client):
        resp = client.get("/api/v1/goal")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "active" in data
        assert "description" in data
        assert "sub_tasks" in data

    def test_cancel_no_active_goal(self, client):
        resp = client.delete("/api/v1/goal")
        assert resp.status_code == 200
        assert "message" in resp.json()["data"]

    def test_cancel_active_goal(self, client):
        # 创建后立即取消
        client.post("/api/v1/goal", json={"description": "test"})
        resp = client.delete("/api/v1/goal")
        assert resp.status_code == 200


class TestLoopAPI:
    def test_create_loop_5m(self, client):
        resp = client.post("/api/v1/loop", json={"interval": "5m", "command": "/goal test"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["loop_id"]
        assert data["status"] == "active"
        assert data["interval_seconds"] == 300

    def test_create_loop_invalid_interval(self, client):
        # P1-5: 非法 interval 格式应被 Pydantic 拒绝
        resp = client.post("/api/v1/loop", json={"interval": "invalid", "command": "test"})
        assert resp.status_code == 422

    def test_create_loop_empty_command(self, client):
        resp = client.post("/api/v1/loop", json={"interval": "5m", "command": ""})
        assert resp.status_code == 422

    def test_list_returns_array(self, client):
        resp = client.get("/api/v1/loop")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["loops"], list)

    def test_stop_nonexistent(self, client):
        # P1-5: 校验响应体内容
        resp = client.delete("/api/v1/loop/nonexistent")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["loop_id"] == "nonexistent"
        assert data["status"] == "stopped"

    def test_goal_pause_returns_501(self, client):
        # P1-3: pause/resume 未实现→501
        resp = client.post("/api/v1/goal/pause")
        assert resp.status_code == 501

    def test_goal_resume_returns_501(self, client):
        resp = client.post("/api/v1/goal/resume")
        assert resp.status_code == 501

    def test_pause_resume(self, client):
        # 先创建一个
        create_resp = client.post("/api/v1/loop", json={"interval": "5m", "command": "test"})
        loop_id = create_resp.json()["data"]["loop_id"]
        pause_resp = client.post(f"/api/v1/loop/{loop_id}/pause")
        assert pause_resp.status_code == 200
        resume_resp = client.post(f"/api/v1/loop/{loop_id}/resume")
        assert resume_resp.status_code == 200
