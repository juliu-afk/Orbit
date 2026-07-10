"""MCP client extended tests — edge cases, disconnect, error paths.
Coverage sprint 7-1: 58% → >=70%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.tools.mcp_client import MCPClientConnection, MCPClientError


class TestMCPClientEdgeCases:
    def test_next_id_increments(self):
        conn = MCPClientConnection("t", "echo", [])
        assert conn._next_id() == 1
        assert conn._next_id() == 2
        assert conn._next_id() == 3

    def test_disconnect_no_process(self):
        """disconnect when never connected → no-op."""
        conn = MCPClientConnection("t", "echo", [])
        conn.disconnect()  # should not raise

    def test_kill_process_no_process(self):
        conn = MCPClientConnection("t", "echo", [])
        conn._kill_process()  # should not raise

    def test_send_request_no_process(self):
        """_send_request without connect → MCPClientError."""
        conn = MCPClientConnection("t", "echo", [])
        with pytest.raises(MCPClientError):
            conn._send_request("test", {})

    def test_connect_file_not_found(self):
        """connect with non-existent command → MCPClientError."""
        conn = MCPClientConnection("test", "/nonexistent/cmd", [])
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            with pytest.raises(MCPClientError):
                conn.connect()

    def test_connect_already_connected(self):
        """connect when already connected → no-op."""
        conn = MCPClientConnection("t", "echo", [])
        conn._connected = True
        conn._process = MagicMock()
        conn.connect()  # should return immediately

    def test_connect_flush_error(self):
        """connect with bad process → MCPClientError."""
        conn = MCPClientConnection("t", "echo", [])
        # Pre-fill queue with response for initialize handshake
        conn._stdout_queue.put((True, '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{}}}'))
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()
        with patch("subprocess.Popen", return_value=mock_proc):
            conn.connect()
            assert conn.connected is True

    def test_call_tool_empty_content(self):
        """call_tool with empty content → empty string."""
        conn = MCPClientConnection("t", "echo", [])
        conn._connected = True
        conn._process = MagicMock()
        conn._process.stdin = MagicMock()
        with patch.object(conn, "_send_request", return_value={"content": []}):
            result = conn.call_tool("test", {})
            assert result == ""

    def test_call_tool_mixed_content(self):
        """call_tool with non-text items → only text items included."""
        conn = MCPClientConnection("t", "echo", [])
        conn._connected = True
        conn._process = MagicMock()
        conn._process.stdin = MagicMock()
        with patch.object(conn, "_send_request", return_value={
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image", "data": "base64..."},
                {"type": "text", "text": "world"},
            ]
        }):
            result = conn.call_tool("test", {})
            assert result == "hello\nworld"

    def test_connect_with_extra_env(self):
        """connect with custom env vars merges into parent env."""
        conn = MCPClientConnection("t", "echo", [], env={"EXTRA": "value"})
        assert "EXTRA" in conn.env
        assert conn.env["EXTRA"] == "value"

    def test_json_decode_error_in_response(self):
        """_send_request with invalid JSON → MCPClientError."""
        conn = MCPClientConnection("t", "echo", [])
        conn._process = MagicMock()
        conn._process.stdin = MagicMock()
        conn._stdout_queue.put((True, "not valid json"))
        with pytest.raises(MCPClientError):
            conn._send_request("test", {})
