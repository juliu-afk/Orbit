"""实时诊断 WebSocket (Step 9 Phase 2.3)——L4 mypy 结果实时推送。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# P1-7: WebSocketException 在 starlette 1.x 不可用，二进制消息会抛 RuntimeError/ValueError
from orbit.lsp.service import DiagnosticService

router = APIRouter(prefix="/lsp", tags=["lsp"])

_diagnostic_service: DiagnosticService | None = None
_active_connections: dict[str, list[WebSocket]] = {}
_conn_lock = asyncio.Lock()  # P1-6: 并发安全


def set_diagnostic_service(svc: DiagnosticService) -> None:
    global _diagnostic_service
    _diagnostic_service = svc


@router.get("/diagnostics")
async def get_diagnostics(task_id: str = "", file: str = ""):
    """HTTP GET /lsp/diagnostics——前端诊断面板轮询。

    P0 修复：前端 stores/diagnostics.ts 调用 /api/v1/lsp/diagnostics，
    此前仅有 WebSocket 端点无 HTTP GET 路由，导致诊断面板 404。
    """
    if not _diagnostic_service:
        return {"code": 0, "data": {"diagnostics": {}}, "message": "服务未初始化"}
    files = [file] if file else []
    results = await _diagnostic_service.get_diagnostics(files) if files else {}
    return {"code": 0, "data": {"diagnostics": results}}


@router.websocket("/ws/diagnostics/{task_id}")
async def diagnostics_ws(ws: WebSocket, task_id: str):
    """WebSocket 端点——连接后推送实时 mypy 诊断结果。"""
    await ws.accept()
    async with _conn_lock:
        conns = _active_connections.setdefault(task_id, [])
        conns.append(ws)
    try:
        while True:
            try:
                data = await ws.receive_text()
            except Exception:
                continue  # P1-7: 忽略二进制/非文本消息
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            if msg.get("action") == "check" and _diagnostic_service:
                files = msg.get("files", [])
                if files:
                    results = await _diagnostic_service.get_diagnostics(files)
                    await ws.send_json({"type": "diagnostics", "data": results})
    except WebSocketDisconnect:
        pass
    finally:
        async with _conn_lock:
            try:
                conns.remove(ws)
            except ValueError:
                pass
            if not conns:
                _active_connections.pop(task_id, None)
