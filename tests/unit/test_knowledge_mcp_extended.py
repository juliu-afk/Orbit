"""knowledge/mcp_server.py extended tests — JSON-RPC helpers, McpServer init."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from orbit.knowledge.mcp_server import McpServer, _make_response, _make_error


class TestJsonRpcHelpers:
    def test_make_response_string_id(self):
        r = _make_response("req-1", {"data": "ok"})
        parsed = json.loads(r)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        assert parsed["result"] == {"data": "ok"}

    def test_make_response_int_id(self):
        r = _make_response(42, ["item1", "item2"])
        parsed = json.loads(r)
        assert parsed["id"] == 42

    def test_make_response_none_id(self):
        r = _make_response(None, {})
        parsed = json.loads(r)
        assert parsed["id"] is None

    def test_make_error(self):
        r = _make_error(1, -32601, "Method not found")
        parsed = json.loads(r)
        assert parsed["error"]["code"] == -32601
        assert parsed["error"]["message"] == "Method not found"

    def test_make_error_with_none_id(self):
        r = _make_error(None, -32700, "Parse error")
        parsed = json.loads(r)
        assert parsed["id"] is None
        assert parsed["error"]["code"] == -32700


class TestMcpServerInit:
    def test_default_init(self):
        s = McpServer()
        assert s._engine is not None
        assert s._workspace_dir == "."
        assert s._code_graph is None

    def test_with_code_graph(self):
        cg = MagicMock()
        s = McpServer(code_graph=cg)
        assert s._code_graph is cg

    def test_with_workspace_dir(self):
        s = McpServer(workspace_dir="/tmp/project")
        assert s._workspace_dir == "/tmp/project"

    def test_has_tools_registered(self):
        s = McpServer()
        assert len(s._tools) > 0
        assert len(s._handlers) > 0

    def test_tools_have_schema(self):
        s = McpServer()
        for name, tool in s._tools.items():
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_run_async_sync_fallback(self):
        """_run_async with no running loop → runs in new event loop."""
        import asyncio
        s = McpServer()

        async def test_coro():
            return "done"

        # Mock no running loop
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            result = s._run_async(test_coro())
            assert result == "done"
