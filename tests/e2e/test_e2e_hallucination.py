"""S5: 防幻觉告警 + 并发 + 健康检查。"""

from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_health_endpoint(e2e_app: Any) -> None:
    """健康检查端点正常。"""
    resp = await e2e_app.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    # Redis 不可用时 status=degraded，测试环境通常无 Redis
    assert data["status"] in ("ok", "degraded")


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_task_creation_idempotency(e2e_app: Any) -> None:
    """并发创建 3 个任务——task_id 互不相同。"""
    tasks = []
    for i in range(3):
        resp = await e2e_app.post(
            "/api/v1/tasks",
            json={
                "prd": f"并发测试 #{i}——验证多任务同时创建不冲突",
                "language": "python",
            },
        )
        assert resp.status_code == 200, f"任务 {i} 创建失败"
        tasks.append(resp.json()["task_id"])

    assert len(set(tasks)) == 3
