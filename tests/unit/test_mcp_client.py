"""MCP 客户端单元测试——模拟子进程 stdin/stdout 交互。

WHY mock subprocess: MCP 协议走子进程 stdin/stdout，
单元测试不启动真实进程——用 pipe 模拟 JSON-RPC 往返。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from orbit.tools.mcp_client import MCPClientConnection, MCPClientError


class TestMCPClientConnection:
    """MCP 客户端连接——生命周期 + JSON-RPC 通信。"""

    def test_init_stores_params_not_connected(self) -> None:
        """构造时存储参数，不立即连接——lazy connect 策略。"""
        conn = MCPClientConnection("test", "echo", ["hello"])
        assert conn.name == "test"
        assert conn.connected is False

    def test_connect_starts_process_and_handshakes(self) -> None:
        """connect() 启动子进程并发送 initialize 请求。"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "serverInfo": {"name": "test-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }) + "\n"

        with patch("subprocess.Popen", return_value=mock_proc):
            conn = MCPClientConnection("test", "fake_cmd", [])
            conn.connect()

            assert conn.connected is True
            write_call = mock_proc.stdin.write.call_args[0][0]
            written = json.loads(write_call)
            assert written["method"] == "initialize"

    def test_connect_file_not_found_gives_helpful_message(self) -> None:
        """命令不存在时给出人类可读提示。"""
        conn = MCPClientConnection("test", "nonexistent_cmd_xyz", [])
        with pytest.raises(MCPClientError, match="命令不存在"):
            conn.connect()

    def test_list_tools_returns_tool_list(self) -> None:
        """list_tools() 发送 tools/list 请求并返回工具列表。"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "serverInfo": {"name": "test", "version": "1.0"},
                    "capabilities": {},
                },
            }) + "\n",
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "find_symbol",
                            "description": "查找符号定义",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name_path": {"type": "string"},
                                },
                                "required": ["name_path"],
                            },
                        },
                    ],
                },
            }) + "\n",
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            conn = MCPClientConnection("test", "fake_cmd", [])
            conn.connect()
            tools = conn.list_tools()

            assert len(tools) == 1
            assert tools[0]["name"] == "find_symbol"

    def test_call_tool_returns_text_content(self) -> None:
        """call_tool() 发送 tools/call 请求并提取 content[0].text。"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"serverInfo": {"name": "test"}, "capabilities": {}},
            }) + "\n",
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "content": [
                        {"type": "text", "text": "def hello(): pass"},
                    ],
                },
            }) + "\n",
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            conn = MCPClientConnection("test", "fake_cmd", [])
            conn.connect()
            result = conn.call_tool("find_symbol", {"name_path": "hello"})

            assert result == "def hello(): pass"

    def test_call_tool_on_disconnected_raises(self) -> None:
        """未连接时调用工具抛 MCPClientError。"""
        conn = MCPClientConnection("test", "fake_cmd", [])
        with pytest.raises(MCPClientError, match="未连接"):
            conn.call_tool("x", {})

    def test_call_tool_error_response_raises(self) -> None:
        """服务器返回 JSON-RPC error 时抛 MCPClientError。"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"serverInfo": {"name": "test"}, "capabilities": {}},
            }) + "\n",
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "error": {"code": -32601, "message": "工具 not_found 未找到"},
            }) + "\n",
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            conn = MCPClientConnection("test", "fake_cmd", [])
            conn.connect()
            with pytest.raises(MCPClientError, match="未找到"):
                conn.call_tool("not_found", {})

    def test_process_exit_during_call_raises(self) -> None:
        """子进程中途崩溃时抛 MCPClientError 含 exit_code。"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"serverInfo": {"name": "test"}, "capabilities": {}},
            }) + "\n",
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            conn = MCPClientConnection("test", "fake_cmd", [])
            conn.connect()
            mock_proc.poll.return_value = 1
            mock_proc.stderr.read.return_value = "Connection reset"

            with pytest.raises(MCPClientError, match="意外退出"):
                conn.call_tool("x", {})


class TestToolRegistryMCP:
    """ToolRegistry MCP 方法——schema 转换 + 工具注册。"""

    def test_convert_mcp_schema_openai_format(self) -> None:
        """MCP inputSchema → OpenAI function calling 格式正确转换。"""
        from orbit.tools.registry import ToolRegistry

        mcp_tool = {
            "name": "find_symbol",
            "description": "查找符号定义并返回其源代码",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name_path": {
                        "type": "string",
                        "description": "符号路径如 MyClass/my_method",
                    },
                    "include_body": {
                        "type": "boolean",
                        "default": True,
                    },
                },
                "required": ["name_path"],
            },
        }

        result = ToolRegistry._convert_mcp_schema("serena/find_symbol", mcp_tool)

        assert result["type"] == "function"
        func = result["function"]
        assert func["name"] == "serena/find_symbol"
        assert func["description"] == "查找符号定义并返回其源代码"
        assert func["parameters"]["type"] == "object"
        assert "name_path" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["name_path"]

    def test_create_mcp_handler_returns_callable(self) -> None:
        """_create_mcp_handler 返回可调用函数——Agent 可透明调用。"""
        from orbit.tools.registry import ToolRegistry

        mock_conn = MagicMock()
        mock_conn.call_tool.return_value = "result text"

        registry = ToolRegistry()
        handler = registry._create_mcp_handler("serena", mock_conn, "find_symbol")

        result = handler(name_path="MyClass", include_body=True)

        mock_conn.call_tool.assert_called_once_with(
            "find_symbol",
            {"name_path": "MyClass", "include_body": True},
        )
        assert result == "result text"

    def test_create_mcp_handler_returns_error_string_on_failure(self) -> None:
        """MCP 调用失败时不抛异常——返回错误字符串给 Agent 处理。"""
        from orbit.tools.registry import ToolRegistry

        mock_conn = MagicMock()
        mock_conn.call_tool.side_effect = MCPClientError("连接超时")

        registry = ToolRegistry()
        handler = registry._create_mcp_handler("serena", mock_conn, "find_symbol")

        result = handler(name_path="X")
        assert "MCP 工具调用失败" in result
        assert "serena/find_symbol" in result
        assert "连接超时" in result
