"""自然语言聊天 API (NL交互 PR #3 + Session PR #1).

WebSocket 端点: ws://host:18888/api/v1/chat
接受文本输入 → 上下文匹配 → 返回项目候选 + 跨项目检测警告。

用法 (前端):
    const ws = new WebSocket("ws://localhost:18888/api/v1/chat");
    ws.send(JSON.stringify({
        type: "chat",
        text: "支付超时了修一下",
        session_id: "abc123",
        project_name: "恪现财务软件",
    }));
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orbit.context.matcher import ContextMatcher
from orbit.projects.registry import ProjectRegistry
from orbit.sessions.registry import SessionRegistry

router = APIRouter(prefix="/chat", tags=["chat"])

_registry = ProjectRegistry()
_session_registry = SessionRegistry()
# WHY 预注册: 确保测试/生产的 ProjectRegistry 至少有一个项目可匹配
if _registry.count() == 0:
    _registry.register(
        "Orbit", description="多Agent开发自循环系统", tags=["agent", "python", "llm"]
    )
_matcher = ContextMatcher(_registry)

# WHY 模块级 import orjson: 避免热路径动态 import
try:
    import orjson as _fast_json
except ImportError:
    _fast_json = None  # type: ignore[assignment]


@router.websocket("")
async def chat_endpoint(ws: WebSocket) -> None:
    """自然语言聊天入口。

    接收 JSON:
      { "type": "chat", "text": "用户输入",
        "session_id": "会话ID", "project_name": "绑定项目" }
    返回 JSON:
      { code, data: MatchResult + cross_project_warning, message }
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            # WHY 防恶意/畸形 JSON: 两次解析均失败时返回错误而非崩溃
            try:
                if _fast_json is not None:
                    payload = _fast_json.loads(raw)
                else:
                    payload = _json.loads(raw)
            except Exception:
                await ws.send_json({"error": "无效的 JSON 格式", "code": 1, "data": None})
                continue

            text = payload.get("text", "")
            session_id = payload.get("session_id", "")  # Session PR #1
            project_name = payload.get("project_name", "")  # Session PR #1
            session_projects = payload.get("session_projects")  # 向后兼容旧协议

            if not text.strip():
                await ws.send_json({"error": "输入为空", "code": 1, "data": None})
                continue

            # 上下文匹配
            result = _matcher.match(text, session_projects=session_projects)

            # ── Session PR #1: 跨项目检测 ──
            cross_warning: str | None = None
            if project_name and result.candidates:
                # WHY 后端检测而非前端：后端有完整 ProjectRegistry，
                # 前端只知道当前项目名，无法判断候选是否属于其他注册项目
                for c in result.candidates:
                    if c.project_name != project_name:
                        cross_warning = c.project_name
                        break

            # ── Session PR #1: 消息持久化 ──
            if session_id:
                try:
                    _session_registry.add_message(
                        session_id=session_id,
                        role="user",
                        content=text,
                        candidates=result.to_dict().get("candidates"),
                        cross_project_warning=cross_warning,
                    )
                    # WHY touch: 聊天活动更新 session 的 updated_at，
                    # 使最近使用的 session 排在列表前面
                    _session_registry.touch(session_id)
                except Exception:
                    # WHY 静默：消息持久化失败不应阻塞聊天功能
                    pass

            # 返回结果（含跨项目警告）
            response_data = result.to_dict()
            response_data["cross_project_warning"] = cross_warning
            response: dict[str, Any] = {
                "code": 0,
                "data": response_data,
                "message": "ok",
            }
            await ws.send_json(response)

    except WebSocketDisconnect:
        pass  # 客户端正常断开
