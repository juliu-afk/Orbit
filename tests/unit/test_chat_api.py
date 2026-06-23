"""NL交互 PR #3——聊天 API WebSocket 测试。"""

import json

from fastapi.testclient import TestClient

from orbit.api.main import create_app


class TestChatWebSocket:
    """NL 聊天 WebSocket 端点。"""

    @classmethod
    def setup_class(cls) -> None:
        cls.client = TestClient(create_app())

    def test_websocket_connect_and_chat(self) -> None:
        """WebSocket 连接 + 发送消息 → 返回候选。"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"text": "Orbit agent 调度"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert "candidates" in data["data"]
            assert "keywords" in data["data"]

    def test_session_history_priority(self) -> None:
        """会话历史优先——指定 session_projects 直接命中。"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({
                "text": "anything",
                "session_projects": ["Orbit"],
            }))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["data"]["source"] == "session"
            assert data["data"]["requires_confirmation"] is False

    def test_empty_text_error(self) -> None:
        """空输入 → 错误响应。"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"text": ""}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 1

    def test_chinese_query(self) -> None:
        """中文查询正常返回。"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            ws.send_text(json.dumps({"text": "财务凭证录入功能优化"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["code"] == 0
            assert len(data["data"]["keywords"]) > 0

    def test_multiple_messages(self) -> None:
        """同一连接发送多条消息。"""
        with self.client.websocket_connect("/api/v1/chat") as ws:
            for _ in range(3):
                ws.send_text(json.dumps({"text": "test"}))
                raw = ws.receive_text()
                data = json.loads(raw)
                assert "code" in data
