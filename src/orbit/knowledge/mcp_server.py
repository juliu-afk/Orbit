"""Step 3.4d MCP Server——JSON-RPC 2.0 over stdio + Phase 1 图谱工具升级。

WHY 手写而非 mcp SDK：MVP 阶段零额外依赖。
MCP 协议足够简单（JSON-RPC 2.0 + tools/list + tools/call）。

12 个 MCP 工具：query_knowledge + find_symbol + find_referencing_symbols +
get_symbols_overview + trace_path + get_architecture + search_code + dead_code +
find_implementations + replace_symbol_body + insert_after/before_symbol + safe_delete_symbol

协议规范：https://spec.modelcontextprotocol.io/
"""
# Reason: Phase 1 — MCP tools 4→12, refactored async pattern, Serena replacement

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Callable
from typing import Any

import structlog

from orbit.knowledge.engine import KnowledgeEngine

logger = structlog.get_logger("orbit.knowledge.mcp")


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

    def __init__(
        self,
        engine: KnowledgeEngine | None = None,
        code_graph: Any = None,
        workspace_dir: str = ".",
    ) -> None:
        self._engine = engine or KnowledgeEngine()
        self._code_graph = code_graph  # CodeGraphEngine 实例（可选）
        self._workspace_dir = workspace_dir
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._register_builtin_tools()

    def _run_async(self, coro):
        """同步 handler 中安全执行异步协程。

        WHY 封装：9 个 handler 都调 CodeGraphEngine async 方法，
        每个重复 asyncio.get_running_loop/try-except ~10 行→消除。
        """
        import asyncio, concurrent.futures
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)

    def set_code_graph(self, code_graph: Any) -> None:
        """注入 CodeGraphEngine——供 main.py 在启动时调用。"""
        self._code_graph = code_graph
        # 重新注册代码工具——code_graph 就绪后
        self._register_code_tools()

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
        # 代码工具——如果 code_graph 已注入则注册
        if self._code_graph is not None:
            self._register_code_tools()

    def _register_code_tools(self) -> None:
        """注册代码导航工具——基于 CodeGraph AST 索引。

        WHY: 让外部 Agent（Claude Code/Codex）能通过 Orbit MCP 做代码导航，
        不再仅限领域知识查询。50 行实现，偷师 Serena 的 MCP 开放思路。
        """
        self.register_tool(
            name="find_symbol",
            description="在代码库中查找符号（函数/类/变量）的定义位置，返回文件路径和行号。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "符号名称，如 MyClass 或 my_function",
                    },
                },
                "required": ["symbol"],
            },
            handler=self._handle_find_symbol,
        )
        self.register_tool(
            name="find_referencing_symbols",
            description="查找所有调用了指定符号的位置（反向调用图）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "被调用的符号名称",
                    },
                },
                "required": ["symbol"],
            },
            handler=self._handle_find_referencing_symbols,
        )
        self.register_tool(
            name="get_symbols_overview",
            description="获取文件的符号大纲——列出所有类、方法、函数及其行号，~300 tokens 替代全文件读取。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "相对于项目根的源文件路径",
                    },
                },
                "required": ["file_path"],
            },
            handler=self._handle_get_symbols_overview,
        )
        # ── Phase 1 新增：图谱查询工具（借鉴 CBM 设计）───────────
        self.register_tool(
            name="trace_path",
            description="BFS 追踪函数调用路径——谁调了它（callers），它调了谁（callees）。深度 1-5，方向 in/out/both。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "函数名"},
                    "direction": {"type": "string", "enum": ["in", "out", "both"], "default": "both"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                },
                "required": ["symbol"],
            },
            handler=self._handle_trace_path,
        )
        self.register_tool(
            name="get_architecture",
            description="返回项目架构概览——语言/模块数/入口点/热点函数（被调用最多 top10）/路由节点。约 2KB。",
            inputSchema={"type": "object", "properties": {}, "required": []},
            handler=self._handle_get_architecture,
        )
        self.register_tool(
            name="search_code",
            description="在已索引文件中执行文本搜索——结果自动关联对应 CodeNode 符号（按行号匹配）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则模式"},
                    "file_pattern": {"type": "string", "description": "可选 glob 过滤文件名"},
                },
                "required": ["pattern"],
            },
            handler=self._handle_search_code,
        )
        self.register_tool(
            name="dead_code",
            description="检测零调用者的函数——排除 main/app 等入口点。用于清理无用代码。",
            inputSchema={"type": "object", "properties": {}, "required": []},
            handler=self._handle_dead_code,
        )
        self.register_tool(
            name="find_implementations",
            description="查找指定类的所有子类实现——通过继承边（INHERITS）。替代 Serena find_implementations。",
            inputSchema={
                "type": "object",
                "properties": {"class_name": {"type": "string", "description": "基类/接口名"}},
                "required": ["class_name"],
            },
            handler=self._handle_find_implementations,
        )
        # ── Phase 1 新增：语义编辑工具（替代 Serena）────────────
        self.register_tool(
            name="replace_symbol_body",
            description="精确替换符号体——通过符号名定位 start/end_line 后替换内容并触增增量索引。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "符号名"},
                    "new_body": {"type": "string", "description": "新代码（不含 def 行）"},
                },
                "required": ["symbol", "new_body"],
            },
            handler=self._handle_replace_symbol_body,
        )
        self.register_tool(
            name="insert_after_symbol",
            description="在指定符号的结束位置之后插入代码。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "code": {"type": "string", "description": "要插入的代码"},
                },
                "required": ["symbol", "code"],
            },
            handler=self._handle_insert_after_symbol,
        )
        self.register_tool(
            name="insert_before_symbol",
            description="在指定符号的起始位置之前插入代码。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["symbol", "code"],
            },
            handler=self._handle_insert_before_symbol,
        )
        self.register_tool(
            name="safe_delete_symbol",
            description="安全删除符号——先检查 edges 表确保零引用（入度=0），再删代码和图谱节点。若存在引用则返回调用者列表。",
            inputSchema={
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
            handler=self._handle_safe_delete_symbol,
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

    # ── 代码导航工具处理器 ──────────────────────────────

    def _handle_find_symbol(self, symbol: str = "", **_: Any) -> dict[str, Any]:
        """查找符号定义——返回文件路径+行号。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化——项目未加载代码图谱"}
        defs = self._run_async(self._code_graph.find_definitions_with_positions(symbol))
        if not defs:
            return {"found": False, "symbol": symbol}
        return {"found": True, "definitions": defs}

    def _handle_find_referencing_symbols(
        self, symbol: str = "", **_: Any
    ) -> dict[str, Any]:
        """查找符号的所有调用者。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化——项目未加载代码图谱"}
        callers = self._run_async(self._code_graph.get_callers(symbol))
        return {"symbol": symbol, "callers": callers}

    def _handle_get_symbols_overview(
        self, file_path: str = "", **_: Any
    ) -> dict[str, Any]:
        """获取文件大纲——AST 解析提取类/方法/函数。"""
        import os
        full_path = os.path.join(self._workspace_dir, file_path)
        try:
            with open(full_path, encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return {"error": f"文件不存在: {file_path}"}
        except Exception as e:
            return {"error": f"读取文件失败: {e}"}

        tree = ast.parse(content)
        items: list[dict[str, Any]] = []
        class_methods: set[str] = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                children = []
                for n in ast.walk(node):
                    if isinstance(n, ast.FunctionDef):
                        class_methods.add(n.name)
                        children.append({"name": n.name, "kind": "method", "line": n.lineno})
                items.append({
                    "name": node.name, "kind": "class",
                    "line": node.lineno, "children": children,
                })
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name not in class_methods:
                items.append({"name": node.name, "kind": "function", "line": node.lineno})
        return {"file": file_path, "symbols": items}

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
    """MCP Server 入口——`python -m orbit.knowledge.mcp_server`。

    自动尝试初始化 CodeGraph，将代码导航工具注册到 MCP。
    失败时降级——仅暴露 query_knowledge 工具。
    """
    code_graph = None
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from orbit.core.config import settings
        from orbit.graph.engines.code_graph import CodeGraphEngine

        db_url = getattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///knowledge.db")
        engine = create_async_engine(db_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        code_graph = CodeGraphEngine(session_factory)
        logger.info("mcp_code_graph_initialized")
    except Exception as e:
        logger.info("mcp_code_graph_unavailable", reason=str(e))

    server = McpServer(code_graph=code_graph)
    server.run()


if __name__ == "__main__":
    main()
