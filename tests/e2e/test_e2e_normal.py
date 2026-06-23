"""S1: 正常流程——调度器执行 → DONE。"""

import asyncio

import pytest

from orbit.api.schemas.task import TaskState


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_normal_flow(e2e_app):
    """完整任务生命周期：调度器 IDLE→PARSING→...→DONE。

    AC2: 30s 内到达 DONE（Mock LLM 秒回，实际 <5s）。

    WHY 直接测调度器而非通过 API 轮询：
    MVP 阶段 API 路由的 _mock_store 与调度器内部状态未打通。
    调度器是核心链路，E2E 验证其完整流水线（LLM→状态转换→检查点→EventBus）。
    """
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    task_id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"  # 固定 task_id 便于调试
    prd = "写出一个冒泡排序函数，包含测试用例"

    state = await asyncio.wait_for(
        scheduler.run_task(task_id, prd),
        timeout=30,
    )
    assert state == TaskState.DONE, f"期望 DONE，实际 {state}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_api_task_create_and_query(e2e_app):
    """API 层：创建任务 → 查询状态。

    验证 REST 契约独立于调度器工作。
    """
    # 创建
    resp = await e2e_app.post("/api/v1/tasks", json={
        "prd": "API 契约测试——验证请求响应格式",
        "language": "python",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["task_id"]) == 32
    assert data["state"] == "IDLE"
    assert data["progress"] == 0.0

    # 查询
    task_id = data["task_id"]
    resp = await e2e_app.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == task_id


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_task_not_found(e2e_app):
    """查询不存在的任务返回 404。"""
    fake_id = "a" * 32
    resp = await e2e_app.get(f"/api/v1/tasks/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_invalid_prd(e2e_app):
    """空 PRD / 超长 PRD 返回 422。"""
    resp = await e2e_app.post("/api/v1/tasks", json={"prd": ""})
    assert resp.status_code == 422

    resp = await e2e_app.post("/api/v1/tasks", json={"prd": "x" * 5001})
    assert resp.status_code == 422

    # 超长
    resp = await e2e_app.post("/api/v1/tasks", json={"prd": "x" * 5001})
    assert resp.status_code == 422
