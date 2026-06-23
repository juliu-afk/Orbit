"""S4: WebSocket 推送——连接 + 错误处理。

用 FastAPI TestClient.websocket_connect 同进程通信。
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_websocket_connect(e2e_app: Any) -> None:
    """WS 连接 → 订阅任务 → 验证连接可建立。

    AC4: WS 端点可访问。
    """
    app = getattr(e2e_app, "_app", None)
    assert app is not None, "app 未注入到 e2e_app"

    resp = await e2e_app.post(
        "/api/v1/tasks",
        json={
            "prd": "WS 测试——验证端点连通性测试",
            "language": "python",
        },
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/dashboard") as ws,
    ):
        ws.send_json({"type": "subscribe", "task_id": task_id})
        assert ws  # 连接存在


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_websocket_invalid_json(e2e_app: Any) -> None:
    """WS 发送非法 JSON → 收到 error 响应。"""
    app = getattr(e2e_app, "_app", None)
    assert app is not None

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/dashboard") as ws,
    ):
        ws.send_text("not json")
        data = ws.receive_json()
        assert data["type"] == "error"
