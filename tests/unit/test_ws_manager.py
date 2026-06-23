"""WebSocket ConnectionManager 单元测试。

Mock WebSocket 对象验证连接管理/订阅/广播/死连接清理。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orbit.ws.manager import ConnectionManager


class MockWebSocket:
    """模拟 FastAPI WebSocket。

    send_json 为 AsyncMock，accept 为同步调用（在 manager.connect 中调）。
    """

    def __init__(self, sid: str = "test-sid"):
        self.sid = sid
        self.send_json = AsyncMock()
        self.accept = AsyncMock()
        self.closed = False


class TestConnectionManager:
    """连接管理器测试。"""

    @pytest.mark.asyncio
    async def test_connect_accepts(self):
        """connect 调用 ws.accept()。"""
        mgr = ConnectionManager()
        ws = MockWebSocket()

        await mgr.connect(ws)
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_rooms(self):
        """disconnect 从所有房间移除该连接。"""
        mgr = ConnectionManager()
        ws = MockWebSocket()

        await mgr.connect(ws)
        await mgr.subscribe(ws, "task-1")
        await mgr.subscribe(ws, "task-2")
        assert len(mgr._rooms) == 2

        await mgr.disconnect(ws)
        assert len(mgr._rooms) == 0  # 空房间自动清理

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_subscribers(self):
        """broadcast 只推送给订阅了该 task 的连接。"""
        mgr = ConnectionManager()
        ws1 = MockWebSocket("ws1")
        ws2 = MockWebSocket("ws2")

        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.subscribe(ws1, "task-1")
        await mgr.subscribe(ws2, "task-2")

        await mgr.broadcast("task-1", {"type": "task:update", "data": "x"})

        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_connections(self):
        """广播时 dead WS（RuntimeError）被自动清理。"""
        mgr = ConnectionManager()
        ws = MockWebSocket()
        ws.send_json = AsyncMock(side_effect=RuntimeError("connection lost"))

        await mgr.connect(ws)
        await mgr.subscribe(ws, "task-1")

        # 不应抛异常
        await mgr.broadcast("task-1", {"type": "x"})

        # dead 连接被清理
        assert len(mgr._rooms) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_cleans_empty_room(self):
        """unsubscribe 后空房间自动删除。"""
        mgr = ConnectionManager()
        ws = MockWebSocket()

        await mgr.connect(ws)
        await mgr.subscribe(ws, "task-1")
        assert "task-1" in mgr._rooms

        await mgr.unsubscribe(ws, "task-1")
        assert "task-1" not in mgr._rooms

    @pytest.mark.asyncio
    async def test_broadcast_no_subscribers(self):
        """无订阅者时 broadcast 不抛异常。"""
        mgr = ConnectionManager()
        await mgr.broadcast("nonexistent", {"type": "x"})
        # 不应抛异常
