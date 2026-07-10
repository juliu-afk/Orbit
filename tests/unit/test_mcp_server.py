"""tools/mcp_server.py unit tests — MCPServer methods, JSON-RPC helpers, constants.
Coverage sprint 3-4: 0% → >=70%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.tools.mcp_server import (
    MCP_VERSION,
    _DEFAULT_EXPOSED_TOOLS,
    MCPServer,
)


# ── Constants ─────────────────────────────────────────────


class TestConstants:
    def test_mcp_version(self):
        assert MCP_VERSION == "2024-11-05"

    def test_default_exposed_tools(self):
        assert len(_DEFAULT_EXPOSED_TOOLS) >= 6
        assert "read_file" in _DEFAULT_EXPOSED_TOOLS
        assert "grep" in _DEFAULT_EXPOSED_TOOLS


# ── __init__ ──────────────────────────────────────────────


class TestMCPServerInit:
    def test_default_init(self):
        s = MCPServer()
        assert s._graph is None
        assert s._sandbox is None
        assert s._tools is None
        assert s._allow_write is False

    def test_with_deps(self):
        g, sb, tr = MagicMock(), MagicMock(), MagicMock()
        s = MCPServer(graph=g, sandbox=sb, tools=tr, allow_write=True)
        assert s._graph is g
        assert s._sandbox is sb
        assert s._tools is tr
        assert s._allow_write is True

    def test_custom_exposed_tools(self):
        s = MCPServer(exposed_tools=["read_file", "grep"])
        assert s._exposed == {"read_file", "grep"}

    def test_default_exposed_when_none(self):
        s = MCPServer()
        assert s._exposed == set(_DEFAULT_EXPOSED_TOOLS)


# ── _response / _error / _send_error ──────────────────────


class TestJsonRpcHelpers:
    def test_response(self):
        s = MCPServer()
        r = s._response(1, {"data": "ok"})
        assert r["jsonrpc"] == "2.0"
        assert r["id"] == 1
        assert r["result"] == {"data": "ok"}

    def test_response_none_id(self):
        s = MCPServer()
        r = s._response(None, {"data": "ok"})
        assert r["id"] is None

    def test_error(self):
        s = MCPServer()
        r = s._error(42, -32601, "Method not found")
        assert r["jsonrpc"] == "2.0"
        assert r["id"] == 42
        assert r["error"]["code"] == -32601
        assert r["error"]["message"] == "Method not found"

    def test_send_error(self):
        s = MCPServer()
        with patch("sys.stdout.write") as mock_write:
            with patch("sys.stdout.flush"):
                s._send_error(1, -32700, "Parse error")
                mock_write.assert_called_once()


# ── _tool_description ─────────────────────────────────────


class TestToolDescription:
    def test_known_tool(self):
        s = MCPServer()
        assert s._tool_description("read_file") == "Read file contents"

    def test_unknown_tool(self):
        s = MCPServer()
        desc = s._tool_description("unknown_tool")
        assert "Orbit tool" in desc


# ── _tool_schema ──────────────────────────────────────────


class TestToolSchema:
    def test_known_schema(self):
        s = MCPServer()
        schema = s._tool_schema("read_file")
        assert schema["type"] == "object"
        assert "path" in schema["properties"]

    def test_unknown_schema(self):
        s = MCPServer()
        schema = s._tool_schema("custom_tool")
        assert schema["type"] == "object"
        assert schema["properties"] == {}


# ── _list_tools ───────────────────────────────────────────


class TestListTools:
    def test_returns_sorted_tools(self):
        s = MCPServer(exposed_tools=["read_file", "grep"])
        tools = s._list_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "grep"  # sorted
        assert tools[1]["name"] == "read_file"

    def test_each_tool_has_schema(self):
        s = MCPServer(exposed_tools=["read_file"])
        tools = s._list_tools()
        assert "inputSchema" in tools[0]
        assert "description" in tools[0]


# ── _graph_query ──────────────────────────────────────────


class TestGraphQuery:
    def test_no_graph(self):
        s = MCPServer()
        assert s._graph_query("code_graph_search", {"query": "foo"}) == "{}"

    def test_code_graph_search(self):
        g = MagicMock()
        g.search.return_value = [{"name": "foo"}]
        s = MCPServer(graph=g)
        result = s._graph_query("code_graph_search", {"query": "foo"})
        assert "foo" in result

    def test_code_graph_symbols(self):
        g = MagicMock()
        g.get_symbols.return_value = [{"name": "bar"}]
        s = MCPServer(graph=g)
        result = s._graph_query("code_graph_symbols", {"path": "/x.py"})
        assert "bar" in result

    def test_unknown_query(self):
        g = MagicMock()
        s = MCPServer(graph=g)
        assert s._graph_query("unknown", {}) == "{}"


# ── _handle ───────────────────────────────────────────────


class TestHandle:
    """Test _handle() — JSON-RPC method routing."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        s = MCPServer()
        resp = await s._handle({"id": 1, "method": "initialize", "params": {}})
        assert resp["result"]["protocolVersion"] == MCP_VERSION
        assert resp["result"]["serverInfo"]["name"] == "orbit-mcp"

    @pytest.mark.asyncio
    async def test_notifications_initialized(self):
        s = MCPServer()
        resp = await s._handle({"id": 2, "method": "notifications/initialized", "params": {}})
        assert resp is None

    @pytest.mark.asyncio
    async def test_tools_list(self):
        s = MCPServer(exposed_tools=["grep"])
        resp = await s._handle({"id": 3, "method": "tools/list", "params": {}})
        assert "tools" in resp["result"]

    @pytest.mark.asyncio
    async def test_unknown_method(self):
        s = MCPServer()
        resp = await s._handle({"id": 4, "method": "unknown", "params": {}})
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_tools_call_unexposed(self):
        s = MCPServer(exposed_tools=["read_file"])
        resp = await s._handle({
            "id": 5, "method": "tools/call",
            "params": {"name": "exec_command", "arguments": {}},
        })
        assert resp["error"]["code"] == -32602


# ── _call_tool ────────────────────────────────────────────


class TestCallTool:
    @pytest.mark.asyncio
    async def test_tool_not_exposed(self):
        s = MCPServer(exposed_tools=[])
        resp = await s._call_tool(1, "exec_command", {})
        assert resp["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_with_tool_registry(self):
        """dispatch is async, so mock must return awaitable."""
        async def mock_dispatch(name, args, agent_name):
            return "result from tool"

        tr = MagicMock()
        tr.dispatch = mock_dispatch
        s = MCPServer(tools=tr, exposed_tools=["test_tool"])
        resp = await s._call_tool(2, "test_tool", {"arg": 1})
        assert resp["result"]["content"][0]["text"] == "result from tool"

    @pytest.mark.asyncio
    async def test_no_handler(self):
        s = MCPServer(exposed_tools=["unknown_tool"])
        resp = await s._call_tool(3, "unknown_tool", {})
        assert resp["error"]["code"] == -32603

    @pytest.mark.asyncio
    async def test_exception_handled_as_error(self):
        tr = MagicMock()
        tr.dispatch.side_effect = RuntimeError("boom")
        s = MCPServer(tools=tr, exposed_tools=["failing_tool"])
        resp = await s._call_tool(4, "failing_tool", {})
        assert resp["result"]["isError"] is True
        assert "boom" in resp["result"]["content"][0]["text"]
