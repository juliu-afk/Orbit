"""自然语言聊天 API (NL交互 PR #3).

WebSocket 端点: ws://host:18888/api/v1/chat
接受文本输入 → 上下文匹配 → 返回项目候选。

用法 (前端):
    const ws = new WebSocket("ws://localhost:18888/api/v1/chat");
    ws.send(JSON.stringify({ text: "支付超时了修一下" }));
    ws.onmessage = (e) => {
        const result = JSON.parse(e.data);
        // result.candidates: [{ project, score, reason, keywords }]
    };
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orbit.context.matcher import ContextMatcher
from orbit.projects.registry import ProjectRegistry

router = APIRouter(prefix="/chat", tags=["chat"])

_registry = ProjectRegistry()
# WHY 预注册: 确保测试/生产的 ProjectRegistry 至少有一个项目可匹配
if _registry.count() == 0:
    _registry.register(
        "Orbit", description="多Agent开发自循环系统", tags=["agent", "python", "llm"]
    )
_matcher = ContextMatcher(_registry)


@router.websocket("")
async def chat_endpoint(ws: WebSocket) -> None:
    """自然语言聊天入口。

    接收 JSON: { "text": "用户输入", "session_projects": ["最近项目"] }
    返回 JSON: MatchResult.to_dict()
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                import orjson

                payload = orjson.loads(raw)
            except Exception:
                import json

                payload = json.loads(raw)

            text = payload.get("text", "")
            session_projects = payload.get("session_projects")

            if not text.strip():
                await ws.send_json({"error": "输入为空", "code": 1, "data": None})
                continue

            # 上下文匹配
            result = _matcher.match(text, session_projects=session_projects)

            # 返回结果
            response: dict[str, Any] = {
                "code": 0,
                "data": result.to_dict(),
                "message": "ok",
            }
            await ws.send_json(response)

    except WebSocketDisconnect:
        pass  # 客户端正常断开
