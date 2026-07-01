"""WebSocket 连接管理器。

WHY 手写而非 Socket.IO：原生 WebSocket 足够简单——
连接→订阅 task_id→推送，50 行代码替代一个第三方库。
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    """WebSocket 连接 + 任务订阅管理。

    数据结构 {task_id: {WebSocket, ...}}。
    一个 task 可被多个客户端订阅（多 Tab/多运维视角）。
    """

    # P1 RSCK-6: 最大连接数——防止无上限增长耗尽内存
    MAX_CONNECTIONS = 200

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._total_connections = 0

    async def connect(self, ws: WebSocket) -> None:
        """接受连接。不做认证（PRD Non-Goal：生产由反向代理处理）。"""
        if self._total_connections >= self.MAX_CONNECTIONS:
            await ws.close(code=1013, reason="服务器连接数已达上限")
            logger.warning("ws_connection_limit_reached", max=self.MAX_CONNECTIONS)
            return
        self._total_connections += 1
        await ws.accept()

    async def disconnect(self, ws: WebSocket) -> None:
        """从所有房间移除该连接。

        WHY list(self._rooms)：遍历时可能删除房间（空房间清理），
        先快照 keys 避免 RuntimeError。
        """
        self._total_connections = max(0, self._total_connections - 1)
        initial_rooms = len(self._rooms)
        for task_id in list(self._rooms):
            self._rooms[task_id].discard(ws)
            if not self._rooms[task_id]:
                del self._rooms[task_id]
        logger.info("ws_disconnect", rooms_cleaned=initial_rooms - len(self._rooms))

    async def subscribe(self, ws: WebSocket, task_id: str) -> None:
        """客户端订阅任务推送。"""
        if task_id not in self._rooms:
            self._rooms[task_id] = set()
        self._rooms[task_id].add(ws)
        logger.info("ws_subscribe", task_id=task_id)

    async def unsubscribe(self, ws: WebSocket, task_id: str) -> None:
        """客户端取消订阅。空房间自动清理。"""
        if task_id in self._rooms:
            self._rooms[task_id].discard(ws)
            if not self._rooms[task_id]:
                del self._rooms[task_id]

    async def broadcast(self, task_id: str, data: dict[str, Any]) -> None:
        """向订阅某 task 的所有客户端推送。

        WHY 清理死连接：WebSocket 可能因网络中断未触发 disconnect，
        send_json 时 RuntimeError 表示连接已死，批量清理。
        """
        if task_id not in self._rooms:
            return
        dead: set[WebSocket] = set()
        for ws in self._rooms[task_id]:
            try:
                await ws.send_json(data)
            except RuntimeError:
                dead.add(ws)
        if dead:
            self._rooms[task_id] -= dead
            if not self._rooms[task_id]:
                del self._rooms[task_id]
