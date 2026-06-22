"""集成测试：FastAPI 应用健康检查 + 任务创建。

验证 API 路由注册正确、请求/响应序列化正常。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from orbit.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_check(client):
    """健康检查返回 status=ok + version。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_create_task_validation(client):
    """PRD 太短时返回 422。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={"prd": "short", "language": "python"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_success(client):
    """合法请求返回 200 + task_id。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "构建一个简单的 Python 计算器应用，支持加减乘除运算",
            "language": "python",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["state"] == "IDLE"


@pytest.mark.asyncio
async def test_get_nonexistent_task(client):
    """查询不存在的任务返回 404。"""
    resp = await client.get("/api/v1/tasks/nonexistent-id")
    assert resp.status_code == 404
