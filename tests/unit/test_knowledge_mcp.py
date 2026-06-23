"""Step 3.4d McpServer 单元测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from orbit.knowledge.engine import KnowledgeEngine
from orbit.knowledge.mcp_server import McpServer, _make_error, _make_response
from orbit.knowledge.store import KnowledgeStore


class TestMcpServer:
    """MCP JSON-RPC 协议——工具列表/调用/错误处理。"""

    @pytest.fixture
    def server(self) -> McpServer:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        engine = KnowledgeEngine(store=store)
        s = McpServer(engine=engine)
        yield s
        store.close(cleanup=True)

    def _request(self, server: McpServer, method: str, params: dict | None = None, req_id: int = 1) -> dict:
        raw = server._handle_request({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        })
        assert raw is not None
        return json.loads(raw)

    def test_tools_list(self, server: McpServer) -> None:
        """tools/list 返回注册的工具。"""
        resp = self._request(server, "tools/list")
        tools = resp["result"]["tools"]
        assert len(tools) >= 1
        names = [t["name"] for t in tools]
        assert "query_knowledge" in names

    def test_tools_call_exact(self, server: McpServer) -> None:
        """tools/call query_knowledge exact 模式。"""
        resp = self._request(server, "tools/call", {
            "name": "query_knowledge",
            "arguments": {"domain": "accounting", "concept": "ROE", "mode": "exact"},
        })
        content = resp["result"]["content"][0]["text"]
        data = json.loads(content)
        assert data["found"] is True
        assert "净资产收益率" in data["content"]

    def test_tools_call_not_found(self, server: McpServer) -> None:
        """不存在的概念返回 found=False。"""
        resp = self._request(server, "tools/call", {
            "name": "query_knowledge",
            "arguments": {"concept": "NonExistent"},
        })
        content = resp["result"]["content"][0]["text"]
        data = json.loads(content)
        assert data["found"] is False

    def test_tools_call_unknown_tool(self, server: McpServer) -> None:
        """调用未注册工具返回错误。"""
        resp = self._request(server, "tools/call", {
            "name": "unknown_tool",
            "arguments": {},
        }, req_id=2)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_initialize(self, server: McpServer) -> None:
        """initialize 返回协议版本和服务信息。"""
        resp = self._request(server, "initialize")
        result = resp["result"]
        assert result["protocolVersion"] == "0.1.0"
        assert result["serverInfo"]["name"] == "orbit-knowledge"

    def test_notification_no_response(self, server: McpServer) -> None:
        """通知（无 id）不返回响应。"""
        raw = server._handle_request({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        assert raw is None

    def test_unknown_method_error(self, server: McpServer) -> None:
        """未知方法返回错误。"""
        resp = self._request(server, "unknown/method")
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_register_custom_tool(self, server: McpServer) -> None:
        """注册自定义工具成功。"""
        server.register_tool(
            name="test_tool",
            description="测试工具",
            inputSchema={"type": "object", "properties": {}},
            handler=lambda **kw: {"ok": True},
        )
        resp = self._request(server, "tools/list")
        tools = [t["name"] for t in resp["result"]["tools"]]
        assert "test_tool" in tools


class TestJsonRpcHelpers:
    """JSON-RPC 辅助函数。"""

    def test_make_response(self) -> None:
        resp = json.loads(_make_response(1, {"key": "value"}))
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["key"] == "value"

    def test_make_error(self) -> None:
        resp = json.loads(_make_error(2, -32000, "test error"))
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 2
        assert resp["error"]["code"] == -32000
        assert resp["error"]["message"] == "test error"
