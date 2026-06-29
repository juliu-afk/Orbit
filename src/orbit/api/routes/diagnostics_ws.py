"""实时诊断 WebSocket (Step 9 Phase 2.3)——L4 mypy 结果实时推送。"""
from __future__ import annotations
import asyncio, json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from orbit.lsp.service import DiagnosticService

router = APIRouter()

_diagnostic_service: DiagnosticService | None = None
_active_connections: dict[str, list[WebSocket]] = {}

def set_diagnostic_service(svc: DiagnosticService) -> None:
    global _diagnostic_service; _diagnostic_service = svc

@router.websocket("/ws/diagnostics/{task_id}")
async def diagnostics_ws(ws: WebSocket, task_id: str):
    """WebSocket 端点——连接后推送实时 mypy 诊断结果。"""
    await ws.accept()
    conns = _active_connections.setdefault(task_id, [])
    conns.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "check" and _diagnostic_service:
                files = msg.get("files", [])
                if files:
                    results = await _diagnostic_service.get_diagnostics(files)
                    await ws.send_json({"type": "diagnostics", "data": results})
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        conns.remove(ws)
        if not conns:
            _active_connections.pop(task_id, None)

def set_diag_service(svc) -> None:
    """别名——供 main.py 使用。"""
    set_diagnostic_service(svc)
