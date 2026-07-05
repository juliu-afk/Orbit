"""MCP Server 暴露 (Phase D3).

WHY:
  Orbit 已有 MCP Client (mcp_client.py)——消费外部 MCP 工具。
  但 Orbit 自身的工具（code_graph, sandbox, hallucination, checkpoint）
  不能被外部 Agent 调用。MCP Server 将 Orbit 工具暴露为标准 MCP 协议，
  让外部 Agent (如 Claude Code, Cursor, Serena) 发现和调用。

设计:
  - JSON-RPC 2.0 over stdio (标准 MCP transport)
  - tools/list + tools/call 两个核心方法
  - 暴露的工具子集: code_graph query, sandbox execute(受限), knowledge search
  - RBAC: 只读工具默认开放，写工具需显式授权
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.sandbox.executor import Sandbox
    from orbit.tools.registry import ToolRegistry

import structlog

logger = structlog.get_logger("orbit.tools.mcp_server")

# MCP 协议版本
MCP_VERSION = "2024-11-05"

# 默认暴露的只读工具
_DEFAULT_EXPOSED_TOOLS: list[str] = [
    "read_file", "grep", "glob", "list_dir",
    "code_graph_search", "code_graph_symbols",
    "knowledge_search", "knowledge_query",
]


class MCPServer:
    """MCP Server——将 Orbit 工具暴露为 MCP 协议供外部 Agent 调用。

    用法:
        server = MCPServer(graph=graph, sandbox=sandbox, tools=tools)
        await server.run()  # 阻塞，stdio 通信

    协议 (JSON-RPC 2.0):
        → {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
        ← {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}
        → {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_file","arguments":{"path":"x.py"}}}
        ← {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"..."}]}}
    """

    def __init__(
        self,
        graph: CodeGraphEngine | None = None,
        sandbox: Sandbox | None = None,
        tools: ToolRegistry | None = None,
        exposed_tools: list[str] | None = None,
        allow_write: bool = False,
    ) -> None:
        self._graph = graph
        self._sandbox = sandbox
        self._tools = tools
        self._exposed = set(exposed_tools or _DEFAULT_EXPOSED_TOOLS)
        self._allow_write = allow_write

    async def run(self) -> None:
        """MCP stdio 主循环——读取 stdin JSON-RPC，处理，写入 stdout。"""
        logger.info("mcp_server_start", exposed_tools=sorted(self._exposed))
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self._send_error(None, -32700, "Parse error")
                    continue
                response = await self._handle(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
        except KeyboardInterrupt:
            pass
        logger.info("mcp_server_stop")

    async def _handle(self, request: dict) -> dict | None:
        """处理单个 JSON-RPC 请求。"""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "initialize":
            return self._response(req_id, {
                "protocolVersion": MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "orbit-mcp", "version": "0.32"},
            })

        if method == "notifications/initialized":
            return None  # 不需要响应

        if method == "tools/list":
            return self._response(req_id, {
                "tools": self._list_tools(),
            })

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            return await self._call_tool(req_id, tool_name, tool_args)

        return self._error(req_id, -32601, f"Method not found: {method}")

    def _list_tools(self) -> list[dict]:
        """列出所有暴露的工具及其 schema。"""
        tools = []
        for name in sorted(self._exposed):
            schema = {
                "name": name,
                "description": self._tool_description(name),
                "inputSchema": self._tool_schema(name),
            }
            tools.append(schema)
        return tools

    async def _call_tool(self, req_id, name: str, args: dict) -> dict:
        """调用工具并返回 MCP 格式结果。"""
        if name not in self._exposed:
            return self._error(req_id, -32602, f"Tool not exposed: {name}")

        try:
            if self._tools:
                result = await self._tools.dispatch(name, args, agent_name="mcp_external")
            elif self._sandbox and name in ("read_file", "exec_command"):
                result = await self._sandbox.execute(name, args)
            elif self._graph and name.startswith("code_graph"):
                result = self._graph_query(name, args)
            else:
                return self._error(req_id, -32603, f"No handler for: {name}")

            # MCP 标准响应格式
            text = str(result)[:10000]  # 截断
            return self._response(req_id, {
                "content": [{"type": "text", "text": text}],
            })
        except Exception as e:
            return self._response(req_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    def _graph_query(self, name: str, args: dict) -> str:
        """图查询——不通过 tools dispatch。"""
        if self._graph is None:
            return "{}"
        if name == "code_graph_search":
            query = args.get("query", "")
            results = self._graph.search(query)
            return json.dumps(results[:20], ensure_ascii=False)
        if name == "code_graph_symbols":
            path = args.get("path", "")
            symbols = self._graph.get_symbols(path)
            return json.dumps(symbols, ensure_ascii=False)
        return "{}"

    def _tool_description(self, name: str) -> str:
        descriptions = {
            "read_file": "Read file contents",
            "grep": "Search file contents with regex",
            "glob": "Find files matching pattern",
            "list_dir": "List directory contents",
            "code_graph_search": "Search code symbols by name/type",
            "code_graph_symbols": "Get all symbols in a file",
            "knowledge_search": "Search Orbit knowledge base",
            "knowledge_query": "Query Orbit knowledge graph",
        }
        return descriptions.get(name, f"Orbit tool: {name}")

    def _tool_schema(self, name: str) -> dict:
        """简化的 JSON Schema——MCP 要求。"""
        schemas = {
            "read_file": {"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},
            "grep": {"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]},
            "glob": {"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]},
            "code_graph_search": {"type":"object","properties":{"query":{"type":"string"}},"required":["query"]},
            "code_graph_symbols": {"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},
            "knowledge_search": {"type":"object","properties":{"query":{"type":"string"}},"required":["query"]},
        }
        return schemas.get(name, {"type":"object","properties":{}})

    # ── JSON-RPC helpers ──────────────────────────────

    def _response(self, req_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def _send_error(self, req_id, code: int, message: str) -> None:
        sys.stdout.write(json.dumps(self._error(req_id, code, message), ensure_ascii=False) + "\n")
        sys.stdout.flush()
