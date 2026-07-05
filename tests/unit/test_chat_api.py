"""Chat API WebSocket tests (ChatterAgent + ClarifierAgent integration).

WHY 双 Agent 测试: chat 端点现在走 ChatterAgent 首触 → 意图路由。
测试环境无 LLM，ChatterAgent 走 mock 模式返回 intent="chat"。
"""

import json

from fastapi.testclient import TestClient

from orbit.api.main import create_app


class TestChatWebSocket:
    """Test ChatterAgent + ClarifierAgent response flow."""

    @classmethod
    def setup_class(cls) -> None:
        cls.client = TestClient(create_app())

    def test_websocket_connect_and_chat(self) -> None:
        """WebSocket connect and send chat message → ChatterAgent responds."""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": "Orbit agent ??"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            # WHY mock 模式: 无 LLM 注入时 ChatterAgent 返回 intent="chat"
            assert data["data"]["type"] in ("chat", "clarify")
            assert "reply" in data["data"]
            assert data["data"]["agent_role"] in ("Chatter", "Clarifier")

    def test_session_history_priority(self) -> None:
        """Session history priority with session_projects."""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "chat",
                        "text": "anything",
                        "session_projects": ["Orbit"],
                    }
                )
            )
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert data["data"]["type"] in ("chat", "clarify")

    def test_empty_text_error(self) -> None:
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": ""}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 1

    def test_chinese_query(self) -> None:
        """Chinese query returns valid Agent response."""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": "Orbit agent scheduling"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert data["data"]["type"] in ("chat", "clarify")
            assert len(data["data"]["reply"]) > 0

    def test_multiple_messages(self) -> None:
        with self.client.websocket_connect("/api/v1/chat") as ws:
            for _ in range(3):
                ws.send_text(json.dumps({"type": "chat", "text": "test message"}))
                raw = ws.receive_text()
                data = json.loads(raw)
                assert data["code"] == 0

    def test_unknown_type_error(self) -> None:
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "unknown_type", "text": "test"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 1

    def test_confirm_without_prd_error(self) -> None:
        """Confirm without PRD returns error."""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "type": "confirm",
                        "session_id": "",
                        "project_name": "",
                    }
                )
            )
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 1
