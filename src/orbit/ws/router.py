"""WebSocket 端点 + 广播协程。

WHY 路由写独立文件：main.py 只组装 app，路由逻辑隔离。
FastAPI 原生 websocket 端点，无需第三方库。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orbit.events.bus import EventBus
from orbit.ws.manager import ConnectionManager

router = APIRouter()
manager = ConnectionManager()


async def start_broadcaster(bus: EventBus) -> None:
    """后台协程：消费 EventBus → 推送到订阅客户端。

    WHY 独立协程：避免调度器 publish() 直接 await ws.send_json()
    阻塞状态机。广播是 I/O 密集操作，放到后台不拖累核心链路。
    """
    while True:
        event = await bus.subscribe()
        await manager.broadcast(event.task_id, {
            "type": event.type,
            "task_id": event.task_id,
            "payload": event.payload,
            "timestamp": event.timestamp.isoformat(),
        })


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """驾驶舱 WebSocket 端点。

    协议（JSON 帧）：
    - C→S: {"type": "subscribe", "task_id": "<uuid4 hex>"}
    - C→S: {"type": "unsubscribe", "task_id": "<uuid4 hex>"}
    - S→C: {"type": "task:update", "task_id": "...", "payload": {...}}
    - S→C: {"type": "token:update", "task_id": "...", "payload": {...}}
    - S→C: {"type": "alert:new", "task_id": "...", "payload": {...}}
    """
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "invalid JSON"},
                })
                continue

            msg_type = msg.get("type")
            task_id = msg.get("task_id", "")

            if msg_type == "subscribe" and task_id:
                await manager.subscribe(websocket, task_id)
            elif msg_type == "unsubscribe" and task_id:
                await manager.unsubscribe(websocket, task_id)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
