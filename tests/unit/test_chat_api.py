"""NL?? PR #3 + ???? Agent ?????? API WebSocket ???

????????chat ???? ClarifierAgent??? {type: clarify, reply, clarification_status, ...}?
?? keywords/source/candidates ??????????? data?candidates ??????????
"""

import json

from fastapi.testclient import TestClient

from orbit.api.main import create_app


class TestChatWebSocket:
    """NL ?? WebSocket ???ClarifierAgent ?????"""

    @classmethod
    def setup_class(cls) -> None:
        cls.client = TestClient(create_app())

    def test_websocket_connect_and_chat(self) -> None:
        """WebSocket ?? + ???? ? ?? ClarifierAgent clarify ???"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": "Orbit agent ??"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert data["data"]["type"] == "clarify"
            assert "reply" in data["data"]
            assert data["data"]["clarification_status"] == "clarifying"

    def test_session_history_priority(self) -> None:
        """? session_projects ????????????candidates ????"""
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
            assert data["data"]["type"] == "clarify"

    def test_empty_text_error(self) -> None:
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": ""}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 1

    def test_chinese_query(self) -> None:
        """???????? Agent ???"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"type": "chat", "text": "??????????"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert data["data"]["type"] == "clarify"
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
            assert data["code"] == 1

    def test_confirm_without_prd_error(self) -> None:
        """confirm ?? modified_prd ? ?????"""
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
