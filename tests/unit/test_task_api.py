"""Step 1.1 API 契约测试（PRD+ADR 原子化用例）。

验证：
- AC1: /docs Swagger UI 可访问
- AC2: 无效 prd（长度<10）返回 422
- 创建任务返回 IDLE
- 查询不存在任务返回 404
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from orbit.api.main import create_app
from orbit.sessions.registry import SessionRegistry


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def session_id() -> str:
    """Session PR #1: 创建测试 Session，返回 session_id 供 Task 测试用。"""
    # WHY 注册项目 + 创建 session: TaskCreateRequest 强制要求 session_id，
    # 必须先有项目 + session 才能测试任务创建
    sr = SessionRegistry()
    try:
        # 确保 project 已存在（由 chat.py 预注册的 "Orbit" 项目）
        s = sr.create("Orbit", title="测试会话")
        return s.session_id
    finally:
        sr.close()


@pytest.mark.asyncio
async def test_health(client):
    """P1 ERR-1: 健康检查验证 Redis 连通性——测试环境无 Redis 时允许 degraded。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_health_degraded_when_redis_fails(client, monkeypatch):
    """P2-3 (PR#138): Redis 不可用时返回 degraded 状态。"""
    async def _mock_ping(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(
        "redis.asyncio.Redis.ping", _mock_ping
    )
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_create_task(client, session_id):
    resp = await client.post(
        "/api/v1/tasks",
        json={"prd": "write a sum function", "session_id": session_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    # task_id 是 uuid4 hex（32 位无连字符）
    assert len(data["task_id"]) == 32
    assert data["state"] == "IDLE"
    assert data["progress"] == 0.0
    # Session PR #1: 响应含 session_id 和 project_name
    assert data["session_id"] == session_id
    assert data["project_name"] == "Orbit"


@pytest.mark.asyncio
async def test_invalid_prd_too_short(client, session_id):
    """AC2: prd 长度 <10 返回 422，错误信息含字段级校验失败。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "short",
            "session_id": session_id,
        },
    )
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    assert any("prd" in str(err["loc"]) for err in errors)


@pytest.mark.asyncio
async def test_invalid_language(client, session_id):
    """language 不在允许列表返回 422。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={"prd": "write a sum function", "language": "rust", "session_id": session_id},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    """查询不存在的任务返回 404，error_code=TASK_NOT_FOUND。"""
    fake_id = "a" * 32
    resp = await client.get(f"/api/v1/tasks/{fake_id}")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error_code"] == "TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_cancel_task(client, session_id):
    """创建后可取消，状态变更为 CANCELLED。"""
    create = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "write a sum function",
            "session_id": session_id,
        },
    )
    task_id = create.json()["task_id"]
    cancel = await client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel.status_code == 200
    # P2-4: 断言状态已改为 CANCELLED
    assert cancel.json()["state"] == "CANCELLED"
    # 再次查询确认状态持久
    query = await client.get(f"/api/v1/tasks/{task_id}")
    assert query.json()["state"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_already_cancelled(client, session_id):
    """重复取消已取消任务返回 409。"""
    create = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "write a sum function",
            "session_id": session_id,
        },
    )
    task_id = create.json()["task_id"]
    await client.post(f"/api/v1/tasks/{task_id}/cancel")
    second = await client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert second.status_code == 409
    assert second.json()["detail"]["error_code"] == "INVALID_STATE"


@pytest.mark.asyncio
async def test_cancel_not_found(client):
    """取消不存在的任务返回 404。"""
    fake_id = "b" * 32
    resp = await client.post(f"/api/v1/tasks/{fake_id}/cancel")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_openapi_schema(client):
    """AC1: OpenAPI schema 可生成（/docs 基于此）。"""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    paths = schema["paths"]
    assert "/api/v1/tasks" in paths
    assert "/api/v1/tasks/{task_id}" in paths
    assert "/api/v1/tasks/{task_id}/cancel" in paths
    assert "/health" in paths


@pytest.mark.asyncio
async def test_prd_boundary_min_length(client, session_id):
    """prd 恰好 10 字符（最小边界）应通过。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "1234567890",
            "session_id": session_id,
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_prd_boundary_too_short(client, session_id):
    """prd 9 字符（边界-1）应返回 422。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "123456789",
            "session_id": session_id,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prd_exceeds_max_length(client, session_id):
    """prd 5001 字符（边界+1）应返回 422。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "x" * 5001,
            "session_id": session_id,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prd_max_boundary(client, session_id):
    """prd 恰好 5000 字符（最大边界）应通过。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "x" * 5000,
            "session_id": session_id,
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_language_allows_javascript(client, session_id):
    """language=javascript 应通过。"""
    resp = await client.post(
        "/api/v1/tasks",
        json={
            "prd": "write a sum function",
            "language": "javascript",
            "session_id": session_id,
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_version_not_hardcoded(client):
    """P2-3: 健康检查返回版本号非空字符串。"""
    resp = await client.get("/health")
    version = resp.json()["version"]
    assert isinstance(version, str)
    assert len(version) > 0
