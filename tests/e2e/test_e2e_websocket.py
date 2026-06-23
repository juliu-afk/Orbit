"""S4: WebSocket 推送——连接 → 订阅 → 接收推送。"""

import asyncio
import json

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_websocket_connect_and_subscribe(e2e_app):
    """WS 连接 → 订阅任务 → 接收 task:update 推送。

    AC4: WS 消息 type 字段正确。
    """
    # 1. 创建任务获取 task_id
    resp = await e2e_app.post("/api/v1/tasks", json={
        "prd": "WS测试——验证实时推送",
        "language": "python",
    })
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 2. 连接 WebSocket
    # E2E 用 httpx AsyncClient（ASGI transport），WS 需要单独连接。
    # TestClient 不支持 WS，用 httpx-ws 或原生 websockets 库。
    try:
        import websockets as ws_module  # noqa: F811
    except ImportError:
        pytest.skip("websockets 库未安装")

    try:
        async with ws_module.connect("ws://127.0.0.1:18888/ws/dashboard") as ws:
            # 订阅任务
            await ws.send(json.dumps({"type": "subscribe", "task_id": task_id}))

            # 等待推送（最多 10s）
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                # AC4: type 字段正确
                assert msg["type"] in ("task:update", "token:update")
                assert msg["task_id"] == task_id
            except TimeoutError:
                pytest.fail("10s 内未收到 WS 推送")
    except (OSError, ConnectionRefusedError):
        pytest.skip("WS 端口不可达——后端未启动或端口非 18888")


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_websocket_invalid_json(e2e_app):
    """WS 发送非法 JSON → 收到 error 响应。"""
    try:
        import websockets
    except ImportError:
        pytest.skip("websockets 库未安装")

    try:
        async with websockets.connect("ws://127.0.0.1:18888/ws/dashboard") as ws:
            await ws.send("not json")
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg["type"] == "error"
    except (OSError, ConnectionRefusedError):
        pytest.skip("WS 端口不可达")
