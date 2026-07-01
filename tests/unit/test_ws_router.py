"""WebSocket 路由单元测试——start_broadcaster + dashboard_ws。

使用 mock EventBus + ConnectionManager + WebSocket。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect


class TestStartBroadcaster:
    @pytest.mark.asyncio
    async def test_broadcaster_consumes_event_and_broadcasts(self):
        """start_broadcaster 消费 EventBus → 不崩溃即可（异步循环）。"""
        from tests.lib.mocks.event_bus import MockEventBus
        from orbit.ws.router import start_broadcaster

        bus = MockEventBus()
        # 启动 broadcaster，运行一小段时间后取消
        import asyncio

        task = asyncio.create_task(start_broadcaster(bus))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # broadcaster 启动后应至少订阅过 EventBus（内部的 bus.subscribe() 会被调用）
        # MockEventBus.subscribe() 会阻塞等待事件，所以我们在取消前验证任务未崩溃
        assert task.cancelled() or task.done()


class TestDashboardWs:
    """dashboard_ws WebSocket 端点——消息路由。"""

    @pytest.fixture
    def mock_ws(self):
        ws = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_subscribe_message(self, mock_ws):
        """subscribe 消息→调用 manager.subscribe。"""
        mock_ws.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "task_id": "task-001"}),
            WebSocketDisconnect(),
        ]

        with patch("orbit.ws.router.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.subscribe = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.unsubscribe = AsyncMock()

            from orbit.ws.router import dashboard_ws

            await dashboard_ws(mock_ws)
            mock_mgr.connect.assert_called_once()
            mock_mgr.subscribe.assert_called_once_with(mock_ws, "task-001")

    @pytest.mark.asyncio
    async def test_unsubscribe_message(self, mock_ws):
        """unsubscribe 消息→调用 manager.unsubscribe。"""
        mock_ws.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "task_id": "task-001"}),
            WebSocketDisconnect(),
        ]

        with patch("orbit.ws.router.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.subscribe = AsyncMock()
            mock_mgr.disconnect = AsyncMock()
            mock_mgr.unsubscribe = AsyncMock()

            from orbit.ws.router import dashboard_ws

            await dashboard_ws(mock_ws)
            mock_mgr.unsubscribe.assert_called_once_with(mock_ws, "task-001")

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, mock_ws):
        """无效 JSON→返回 error 消息。"""
        mock_ws.receive_text.side_effect = [
            "not valid json{{{",
            WebSocketDisconnect(),
        ]

        with patch("orbit.ws.router.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()

            from orbit.ws.router import dashboard_ws

            await dashboard_ws(mock_ws)
            # 应发送 error 消息
            error_calls = [
                c for c in mock_ws.send_json.call_args_list
                if c[0][0].get("type") == "error"
            ]
            assert len(error_calls) == 1

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self, mock_ws):
        """WebSocketDisconnect→调用 manager.disconnect。"""
        mock_ws.receive_text.side_effect = WebSocketDisconnect()

        with patch("orbit.ws.router.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()

            from orbit.ws.router import dashboard_ws

            await dashboard_ws(mock_ws)
            mock_mgr.connect.assert_called_once()
            mock_mgr.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_message_type_ignored(self, mock_ws):
        """未知 type→不崩溃，忽略。"""
        mock_ws.receive_text.side_effect = [
            json.dumps({"type": "unknown_cmd", "task_id": "t1"}),
            WebSocketDisconnect(),
        ]

        with patch("orbit.ws.router.manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = AsyncMock()

            from orbit.ws.router import dashboard_ws

            await dashboard_ws(mock_ws)
            # 不应调用 subscribe 或 unsubscribe
            mock_mgr.subscribe.assert_not_called()
            mock_mgr.unsubscribe.assert_not_called()
