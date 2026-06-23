"""Step 3.4d MCP Server——JSON-RPC 2.0 over stdio。

WHY 手写而非 mcp SDK：MVP 阶段零额外依赖。
MCP 协议足够简单（JSON-RPC 2.0 + tools/list + tools/call），
~100 行实现完整工具注册+调用循环。

协议规范：https://spec.modelcontextprotocol.io/
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import structlog

from orbit.knowledge.engine import KnowledgeEngine

logger = structlog.get_logger()


def _make_response(id_val: int | str | None, result: Any) -> str:
    """构造 JSON-RPC 2.0 响应。"""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": result,
        },
        ensure_ascii=False,
    )


def _make_error(id_val: int | str | None, code: int, message: str) -> str:
    """构造 JSON-RPC 2.0 错误响应。"""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": id_val,
            "error": {"code": code, "message": message},
        },
        ensure_ascii=False,
    )


class McpServer:
    """MCP Server——注册工具 + JSON-RPC 主循环。

    工具注册格式遵循 MCP tools/list 规范：
    {name, description, inputSchema: {type: "object", properties: {...}}}
    """

    def __init__(self, engine: KnowledgeEngine | None = None) -> None:
        self._engine = engine or KnowledgeEngine()
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """注册内置知识查询工具。"""
        self.register_tool(
            name="query_knowledge",
            description="查询领域知识概念。支持精确查询（exact）和语义搜索（semantic）模式。",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "领域：accounting/finance/legal",
                        "default": "accounting",
                    },
                    "concept": {
                        "type": "string",
                        "description": "概念名或自然语言查询",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["exact", "semantic", "hybrid"],
                        "default": "exact",
                        "description": "查询模式",
                    },
                },
                "required": ["concept"],
            },
            handler=self._handle_query_knowledge,
        )

    def register_tool(
        self,
        name: str,
        description: str,
        inputSchema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """注册 MCP 工具。"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": inputSchema,
        }
        self._handlers[name] = handler

    def _handle_query_knowledge(self, **kwargs: Any) -> dict[str, Any]:
        """处理 query_knowledge 工具调用。"""
        domain = kwargs.get("domain", "accounting")
        concept = kwargs.get("concept", "")
        mode = kwargs.get("mode", "exact")

        result = self._engine.query(domain=domain, concept=concept, mode=mode)
        if result is None:
            return {"found": False, "message": f"概念 {domain}/{concept} 不存在"}
        return {"found": True, **result.to_dict()}

    def _handle_request(self, request: dict[str, Any]) -> str | None:
        """处理单个 JSON-RPC 请求，返回响应字符串或 None（通知）。"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "tools/list":
            return _make_response(req_id, {"tools": list(self._tools.values())})

        if method == "tools/call":
            tool_name = params.get("name", "")
            if tool_name not in self._handlers:
                return _make_error(req_id, -32601, f"工具 {tool_name} 未找到")
            try:
                result = self._handlers[tool_name](**params.get("arguments", {}))
                return _make_response(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
                )
            except Exception as e:
                logger.error("mcp_tool_error", tool=tool_name, error=str(e))
                return _make_error(req_id, -32000, str(e))

        if method == "initialize":
            return _make_response(
                req_id,
                {
                    "protocolVersion": "0.1.0",
                    "serverInfo": {"name": "orbit-knowledge", "version": "0.11.0"},
                    "capabilities": {"tools": {}},
                },
            )

        # notifications（无 id）不响应
        if req_id is None:
            return None

        return _make_error(req_id, -32601, f"方法 {method} 未实现")

    def run(self) -> None:
        """MCP JSON-RPC 主循环——stdin 读取，stdout 写入。

        WHY stdin/stdout：MCP 协议标准传输方式，
        与 Claude Desktop/VS Code 等 MCP 客户端直接对接。
        """
        logger.info("mcp_server_started", tools=list(self._tools.keys()))
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self._handle_request(request)
            if response is not None:
                sys.stdout.write(response + "\n")
                sys.stdout.flush()


def main() -> None:
    """MCP Server 入口——`python -m orbit.knowledge.mcp_server`。"""
    server = McpServer()
    server.run()


if __name__ == "__main__":
    main()
