"""Step 3.4d MCP Server——JSON-RPC 2.0 over stdio。

WHY 手写而非 mcp SDK：MVP 阶段零额外依赖。
MCP 协议足够简单（JSON-RPC 2.0 + tools/list + tools/call）。

20 个 MCP 工具：query_knowledge + find_symbol + find_referencing_symbols +
get_symbols_overview + trace_path + get_architecture + search_code + dead_code +
find_implementations + replace_symbol_body + insert_after/before_symbol +
safe_delete_symbol + rename_symbol + type_hierarchy +
query_graph + detect_changes + export_graph_artifact + okf_import + okf_export

协议规范：https://spec.modelcontextprotocol.io/
"""
# Reason: Updated tool count from 4 to 13 per Phase 1 landing plan

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
        """在同步 handler 中安全执行异步协程。

        WHY 统一封装：9 个 handler 都需要调 CodeGraphEngine 的 async 方法，
        每个都重复 asyncio.get_running_loop/try-except 样板 ~10 行太冗余。
        """
        import asyncio, concurrent.futures
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # 已有事件循环（MCP stdio 线程在主循环之外）→ 线程池隔离
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
        不再仅限领域知识查询。
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
        # ── Phase 1 新增：图谱查询工具（借鉴 CBM）──────────────────
        self.register_tool(
            name="trace_path",
            description="BFS 追踪函数的调用路径——谁调了它（callers），它调了谁（callees）。深度 1-5，方向 in/out/both。",
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
            description="返回项目架构概览——语言分布、模块数、入口点、热点函数（被调用最多的前10）、路由节点。约 2KB，适合 preview tier。",
            inputSchema={"type": "object", "properties": {}, "required": []},
            handler=self._handle_get_architecture,
        )
        self.register_tool(
            name="search_code",
            description="在已索引文件中执行文本搜索（grep），结果自动关联对应 CodeNode 符号。仅搜索已索引文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则模式"},
                    "file_pattern": {"type": "string", "description": "可选：glob 过滤文件名"},
                },
                "required": ["pattern"],
            },
            handler=self._handle_search_code,
        )
        self.register_tool(
            name="dead_code",
            description="检测零调用者的函数（排除入口点 main/app/create_app 等）。用于清理无用代码。",
            inputSchema={"type": "object", "properties": {}, "required": []},
            handler=self._handle_dead_code,
        )
        self.register_tool(
            name="find_implementations",
            description="查找指定类的所有子类实现——通过继承边（INHERITS）查询。",
            inputSchema={
                "type": "object",
                "properties": {"class_name": {"type": "string", "description": "基类/接口名"}},
                "required": ["class_name"],
            },
            handler=self._handle_find_implementations,
        )
        # ── Phase 1 新增：语义编辑工具 ────────────────────────────
        self.register_tool(
            name="replace_symbol_body",
            description="精确替换函数/方法的函数体。通过符号名定位 start_line..end_line，替换内容后触增增量索引。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "符号名（函数/方法）"},
                    "new_body": {"type": "string", "description": "新的函数体代码（不含 def 行和缩进）"},
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
                    "symbol": {"type": "string", "description": "符号名"},
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
                    "symbol": {"type": "string", "description": "符号名"},
                    "code": {"type": "string", "description": "要插入的代码"},
                },
                "required": ["symbol", "code"],
            },
            handler=self._handle_insert_before_symbol,
        )
        self.register_tool(
            name="safe_delete_symbol",
            description="安全删除符号——先检查 edges 表确认零引用（入度=0），再删除代码+图谱节点。若存在引用则返回调用者列表。",
            inputSchema={
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "要删除的符号名"}},
                "required": ["symbol"],
            },
            handler=self._handle_safe_delete_symbol,
        )
        # ── 接线：孤立模块 → MCP 工具暴露 ──────────────────────
        self.register_tool(
            name="query_graph",
            description="统一图谱查询——type=code/database/config，支持 symbol/table/key 参数。",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_type": {"type": "string", "enum": ["code", "database", "config"]},
                    "symbol": {"type": "string"},
                    "table": {"type": "string"},
                    "key": {"type": "string"},
                },
                "required": ["graph_type"],
            },
            handler=self._handle_query_graph,
        )
        self.register_tool(
            name="detect_changes",
            description="Git diff 影响分析——返回变更文件中的受影响符号 + 风险分类。",
            inputSchema={
                "type": "object",
                "properties": {"base_ref": {"type": "string", "default": "HEAD~1"}},
                "required": [],
            },
            handler=self._handle_detect_changes,
        )
        self.register_tool(
            name="export_graph_artifact",
            description="导出 zstd 压缩图谱产物——团队共享用。",
            inputSchema={
                "type": "object",
                "properties": {"output_path": {"type": "string", "default": ".orbit/graph/graph.db.zst"}},
                "required": [],
            },
            handler=self._handle_export_artifact,
        )
        self.register_tool(
            name="okf_import",
            description="从 OKF bundle 导入领域知识——支持第三方会计准则/行业知识包。",
            inputSchema={
                "type": "object",
                "properties": {"bundle_dir": {"type": "string", "description": "OKF bundle 目录路径"}},
                "required": ["bundle_dir"],
            },
            handler=self._handle_okf_import,
        )
        self.register_tool(
            name="okf_export",
            description="导出知识图谱为 OKF bundle——人类可用 Obsidian/VS Code 编辑。",
            inputSchema={
                "type": "object",
                "properties": {"output_dir": {"type": "string", "default": ".orbit/knowledge"}},
                "required": [],
            },
            handler=self._handle_okf_export,
        )
        # ── Phase 2 新增：重命名 + 类型层次 ──────────────────
        self.register_tool(
            name="rename_symbol",
            description="工作区级安全重命名——更新所有引用位置+edges表。依赖 Tree-sitter 多语言支持。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "要重命名的符号"},
                    "new_name": {"type": "string", "description": "新名称"},
                },
                "required": ["symbol", "new_name"],
            },
            handler=self._handle_rename_symbol,
        )
        self.register_tool(
            name="type_hierarchy",
            description="返回类的超类型/子类型层次——BFS 沿 INHERITS 边上下遍历。",
            inputSchema={
                "type": "object",
                "properties": {"class_name": {"type": "string", "description": "类名"}},
                "required": ["class_name"],
            },
            handler=self._handle_type_hierarchy,
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

    # ── Phase 1 新增：图谱查询 handler ──────────────────────

    def _handle_trace_path(
        self, symbol: str = "", direction: str = "both", max_depth: int = 3, **_: Any
    ) -> dict[str, Any]:
        """BFS 追踪函数调用路径。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        callers_list: list[dict] = []
        callees_list: list[dict] = []
        visited_in: set[str] = set()
        visited_out: set[str] = set()

        if direction in ("in", "both"):
            current = {symbol}
            visited_in.add(symbol)
            for depth in range(1, max_depth + 1):
                next_level: set[str] = set()
                for sym in current:
                    try:
                        c = self._run_async(self._code_graph.get_callers(sym))
                        for caller_name in c:
                            if caller_name not in visited_in:
                                visited_in.add(caller_name)
                                callers_list.append({"caller": caller_name, "target": sym, "depth": depth})
                                next_level.add(caller_name)
                    except Exception:
                        pass
                current = next_level
                if not current:
                    break

        if direction in ("out", "both"):
            current = {symbol}
            visited_out.add(symbol)
            for depth in range(1, max_depth + 1):
                next_level: set[str] = set()
                for sym in current:
                    try:
                        c = self._run_async(self._code_graph.get_callees(sym))
                        for callee_name in c:
                            if callee_name not in visited_out:
                                visited_out.add(callee_name)
                                callees_list.append({"caller": sym, "callee": callee_name, "depth": depth})
                                next_level.add(callee_name)
                    except Exception:
                        pass
                current = next_level
                if not current:
                    break

        return {
            "symbol": symbol,
            "max_depth": max_depth,
            "direction": direction,
            "callers": callers_list,
            "callees": callees_list,
        }

    def _handle_get_architecture(self, **_: Any) -> dict[str, Any]:
        """聚合查询——架构概览。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        import collections
        try:
            nodes = self._run_async(self._code_graph.get_all_nodes())
            edges = self._run_async(self._code_graph.get_all_edges())
        except Exception as e:
            return {"error": f"查询失败: {e}"}

        # 语言分布
        lang_counter: dict[str, int] = collections.Counter()
        # 模块（namespace）
        modules: set[str] = set()
        # 入口点
        entry_points: list[dict] = []
        entry_names = {"main", "app", "create_app", "run", "serve", "start"}
        functions: list[dict] = []

        for n in nodes:
            fp = n.get("file_path", "")
            if "." in fp:
                lang_counter[fp.rsplit(".", 1)[-1]] += 1
            ns = (n.get("meta") or {}).get("namespace", "")
            if ns:
                modules.add(ns)
            name = n.get("name", "")
            ntype = n.get("type", "")
            if ntype == "function":
                functions.append(n)
                if name in entry_names:
                    entry_points.append({"name": name, "file": fp, "line": n.get("start_line")})

        # 热点：出度 top 10
        out_degree: dict[str, int] = collections.Counter()
        for e in edges:
            if e.get("edge_type") == "calls":
                out_degree[e.get("source_id", "")] += 1
        # 按出度排序取 top 10
        func_degrees = [(f, out_degree.get(f.get("id", ""), 0)) for f in functions]
        func_degrees.sort(key=lambda x: x[1], reverse=True)
        hotspots = [
            {"name": f["name"], "file": f.get("file_path", ""), "call_count": cnt}
            for f, cnt in func_degrees[:10] if cnt > 0
        ]

        return {
            "languages": dict(lang_counter.most_common()),
            "module_count": len(modules),
            "modules": sorted(modules)[:50],  # 截断避免过大
            "entry_points": entry_points,
            "hotspots": hotspots,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def _handle_search_code(
        self, pattern: str = "", file_pattern: str | None = None, **_: Any
    ) -> dict[str, Any]:
        """图谱增强 grep——仅搜索已索引文件，结果关联 CodeNode。"""
        import re, os
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        try:
            nodes = self._run_async(self._code_graph.get_all_nodes())
        except Exception as e:
            return {"error": f"查询节点失败: {e}"}

        # 收集已索引的唯文件路径
        indexed_files: set[str] = set()
        for n in nodes:
            fp = n.get("file_path", "")
            if fp:
                indexed_files.add(fp)

        # 过滤文件
        files_to_search: list[str] = []
        for fp in indexed_files:
            if file_pattern:
                try:
                    if not re.search(file_pattern, fp):
                        continue
                except re.error:
                    pass
            files_to_search.append(fp)

        results: list[dict] = []
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return {"error": f"正则模式无效: {e}"}

        for fp in sorted(files_to_search)[:200]:  # 截断——避免扫描整个项目
            full_path = os.path.join(self._workspace_dir, fp)
            try:
                with open(full_path, encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines, start=1):
                if compiled.search(line):
                    # 按行号匹配 CodeNode
                    matching_symbols = [
                        {"name": n.get("name"), "type": n.get("type")}
                        for n in nodes
                        if n.get("file_path") == fp
                        and n.get("start_line") is not None
                        and n.get("end_line") is not None
                        and n["start_line"] <= i <= n["end_line"]
                    ]
                    results.append({
                        "file": fp,
                        "line": i,
                        "content": line.strip()[:200],
                        "symbols": matching_symbols[:5],
                    })
                    if len(results) >= 100:
                        break
            if len(results) >= 100:
                break

        return {"pattern": pattern, "match_count": len(results), "results": results}

    def _handle_dead_code(self, **_: Any) -> dict[str, Any]:
        """检测零调用者函数（排除入口点）。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        try:
            nodes = self._run_async(self._code_graph.get_all_nodes())
            edges = self._run_async(self._code_graph.get_all_edges())
        except Exception as e:
            return {"error": f"查询失败: {e}"}

        entry_whitelist = {"main", "app", "create_app", "run", "serve", "start", "__init__"}
        # 被调用过的 target_id
        called_ids: set[str] = set()
        for e in edges:
            if e.get("edge_type") == "calls":
                called_ids.add(e.get("target_id", ""))

        dead: list[dict] = []
        for n in nodes:
            if n.get("type") != "function":
                continue
            if n.get("name", "") in entry_whitelist:
                continue
            if n.get("id") not in called_ids:
                dead.append({
                    "name": n.get("name"),
                    "file": n.get("file_path", ""),
                    "line": n.get("start_line"),
                })

        return {"dead_functions": dead, "count": len(dead)}

    def _handle_find_implementations(
        self, class_name: str = "", **_: Any
    ) -> dict[str, Any]:
        """查找类的所有子类实现——通过继承关系。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        try:
            nodes = self._run_async(self._code_graph.get_all_nodes())
            edges = self._run_async(self._code_graph.get_all_edges())
        except Exception as e:
            return {"error": f"查询失败: {e}"}

        # 先找基类的 node_id
        base_id = None
        for n in nodes:
            if n.get("name") == class_name and n.get("type") == "class":
                base_id = n.get("id")
                break

        if base_id is None:
            return {"found": False, "class_name": class_name, "message": "类未找到"}

        # 通过 edges 找所有指向 base_id 的继承边
        sub_ids: set[str] = set()
        for e in edges:
            if e.get("edge_type") == "inherits" and e.get("target_id") == base_id:
                sub_ids.add(e.get("source_id", ""))

        implementations: list[dict] = []
        for n in nodes:
            if n.get("id") in sub_ids:
                implementations.append({
                    "name": n.get("name"),
                    "file": n.get("file_path", ""),
                    "line": n.get("start_line"),
                })

        return {"found": True, "class_name": class_name, "implementations": implementations}

    # ── Phase 1 新增：语义编辑 handler ──────────────────────

    def _get_symbol_location(self, symbol: str) -> dict | None:
        """查找符号的文件路径和行号范围。"""
        if not self._code_graph:
            return None
        try:
            defs = self._run_async(self._code_graph.find_definitions_with_positions(symbol))
            if not defs:
                return None
            return defs[0]
        except Exception:
            return None

    def _handle_replace_symbol_body(
        self, symbol: str = "", new_body: str = "", **_: Any
    ) -> dict[str, Any]:
        """精确替换函数体。"""
        loc = self._get_symbol_location(symbol)
        if loc is None:
            return {"success": False, "error": f"符号 {symbol} 未找到"}
        file_path = loc["file_path"]
        start = loc["start_line"]
        end = loc.get("end_line", start)
        import os
        full_path = os.path.join(self._workspace_dir, file_path)
        try:
            with open(full_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}

        # 保留 def 行和缩进上下文——只替换 body 部分（start_line+1 到 end_line-1 或整个函数）
        # 简单策略：替换 start_line..end_line 之间的内容（含函数签名）
        # 更好策略：找到函数体的 indent 级别，替换 def 行之后的内容
        indent = ""
        def_line = lines[start - 1] if start <= len(lines) else ""
        if def_line:
            indent = def_line[:len(def_line) - len(def_line.lstrip())]

        # 保留 def 行，替换其后的 body
        body_start = start + 1  # def 行之后
        # 构造缩进后的 body
        indented_body = "\n".join(
            (indent + "    " + line) if line.strip() else ""
            for line in new_body.split("\n")
        )
        new_lines = lines[:start] + [indented_body + "\n"] + lines[end:]
        # 备份
        backup = "".join(lines)
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            # 恢复备份
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(backup)
            return {"success": False, "error": f"写入文件失败（已恢复原内容）: {e}"}

        # 增量更新图谱
        try:
            self._run_async(self._code_graph.incremental_update(file_path))
        except Exception:
            pass

        return {"success": True, "symbol": symbol, "file": file_path, "old_lines": f"{start}-{end}"}

    def _handle_insert_after_symbol(
        self, symbol: str = "", code: str = "", **_: Any
    ) -> dict[str, Any]:
        """在符号结束后插入代码。"""
        loc = self._get_symbol_location(symbol)
        if loc is None:
            return {"success": False, "error": f"符号 {symbol} 未找到"}
        file_path = loc["file_path"]
        end = loc.get("end_line", loc["start_line"])
        import os
        full_path = os.path.join(self._workspace_dir, file_path)
        try:
            with open(full_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}
        # 在 end_line 后插入
        insert_at = end
        code_lines = code.split("\n")
        new_lines = lines[:insert_at] + [l + "\n" for l in code_lines] + lines[insert_at:]
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            return {"success": False, "error": str(e)}
        try:
            self._run_async(self._code_graph.incremental_update(file_path))
        except Exception:
            pass
        return {"success": True, "symbol": symbol, "file": file_path, "inserted_after_line": end}

    def _handle_insert_before_symbol(
        self, symbol: str = "", code: str = "", **_: Any
    ) -> dict[str, Any]:
        """在符号开始前插入代码。"""
        loc = self._get_symbol_location(symbol)
        if loc is None:
            return {"success": False, "error": f"符号 {symbol} 未找到"}
        file_path = loc["file_path"]
        start = loc["start_line"]
        import os
        full_path = os.path.join(self._workspace_dir, file_path)
        try:
            with open(full_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}
        insert_at = start - 1
        code_lines = code.split("\n")
        new_lines = lines[:insert_at] + [l + "\n" for l in code_lines] + lines[insert_at:]
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            return {"success": False, "error": str(e)}
        try:
            self._run_async(self._code_graph.incremental_update(file_path))
        except Exception:
            pass
        return {"success": True, "symbol": symbol, "file": file_path, "inserted_before_line": start}

    def _handle_safe_delete_symbol(
        self, symbol: str = "", **_: Any
    ) -> dict[str, Any]:
        """安全删除——先确认零引用再删。"""
        loc = self._get_symbol_location(symbol)
        if loc is None:
            return {"success": False, "error": f"符号 {symbol} 未找到"}
        # 检查引用
        try:
            callers = self._run_async(self._code_graph.get_callers(symbol))
        except Exception:
            callers = []
        if callers:
            return {
                "success": False,
                "symbol": symbol,
                "error": f"符号仍有 {len(callers)} 个调用者",
                "callers": callers[:10],
            }
        # 删除代码
        file_path = loc["file_path"]
        start = loc["start_line"]
        end = loc.get("end_line", start)
        import os
        full_path = os.path.join(self._workspace_dir, file_path)
        try:
            with open(full_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}
        new_lines = lines[:start - 1] + lines[end:]
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            return {"success": False, "error": str(e)}
        try:
            self._run_async(self._code_graph.incremental_update(file_path))
        except Exception:
            pass
        return {"success": True, "symbol": symbol, "file": file_path, "deleted_lines": f"{start}-{end}"}

    # ── Phase 2 新增：重命名 + 类型层次 ──────────────────────

    def _handle_rename_symbol(
        self, symbol: str = "", new_name: str = "", **_: Any
    ) -> dict[str, Any]:
        """工作区级安全重命名——更新所有引用 + edges 表 + CodeNode.name。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        loc = self._get_symbol_location(symbol)
        if loc is None:
            return {"success": False, "error": f"符号 {symbol} 未找到"}
        # 收集所有引用位置
        callers = self._run_async(self._code_graph.get_callers(symbol))
        callees = self._run_async(self._code_graph.get_callees(symbol))
        # 所有引用的文件（调用者文件 + 符号自身文件）
        import os as _os
        files_to_update: set[str] = {loc["file_path"]}
        for caller_name in callers:
            c_loc = self._get_symbol_location(caller_name)
            if c_loc:
                files_to_update.add(c_loc["file_path"])
        # 逐文件替换
        updated = 0
        for fpath in files_to_update:
            full_path = _os.path.join(self._workspace_dir, fpath)
            try:
                with open(full_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            # P2-1 fix: word-boundary regex 防子串误改（order→handleOrder 不误改 border）
            import re as _re
            new_content = _re.sub(r'\b' + _re.escape(symbol) + r'\b', new_name, content)
            if new_content != content:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                updated += 1
                self._run_async(self._code_graph.incremental_update(fpath))
        # P1-2 fix: incremental_update 已删除旧节点+重建——无需手动改 name
        return {"success": True, "symbol": symbol, "new_name": new_name, "files_updated": updated}

    def _handle_type_hierarchy(
        self, class_name: str = "", **_: Any
    ) -> dict[str, Any]:
        """类型层次——BFS 遍历 INHERITS 边返回超类型+子类型。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        try:
            nodes = self._run_async(self._code_graph.get_all_nodes())
            edges = self._run_async(self._code_graph.get_all_edges())
        except Exception as e:
            return {"error": f"查询失败: {e}"}
        # 找目标类的 node_id
        target_id = None
        for n in nodes:
            if n.get("name") == class_name and n.get("type") == "class":
                target_id = n.get("id")
                break
        if target_id is None:
            return {"found": False, "class_name": class_name}
        # P2-2 fix: 预建邻接索引——O(V+E) 替代 O(V×E)
        node_by_id = {n.get("id"): n for n in nodes}
        inherits_to: dict[str, list[str]] = {}   # target_id → [source_ids] (子类)
        inherits_from: dict[str, list[str]] = {} # source_id → [target_ids] (超类)
        for e in edges:
            if e.get("edge_type") == "inherits":
                tid = e.get("target_id", "")
                sid = e.get("source_id", "")
                inherits_to.setdefault(tid, []).append(sid)
                inherits_from.setdefault(sid, []).append(tid)
        # BFS 上行（supertypes）
        supertypes: list[dict] = []
        visited: set[str] = {target_id}
        queue = [target_id]
        for cur in queue:
            for sup_id in inherits_from.get(cur, []):
                if sup_id not in visited:
                    visited.add(sup_id)
                    sn = node_by_id.get(sup_id)
                    if sn:
                        supertypes.append({"name": sn["name"], "file": sn.get("file_path", "")})
                    queue.append(sup_id)
        # BFS 下行（subtypes）
        subtypes: list[dict] = []
        visited2: set[str] = {target_id}
        queue2 = [target_id]
        for cur in queue2:
            for sub_id in inherits_to.get(cur, []):
                if sub_id not in visited2:
                    visited2.add(sub_id)
                    sn = node_by_id.get(sub_id)
                    if sn:
                        subtypes.append({"name": sn["name"], "file": sn.get("file_path", "")})
                    queue2.append(sub_id)
        return {"found": True, "class_name": class_name,
                "supertypes": supertypes, "subtypes": subtypes}

    # ── 接线 handler：孤立模块 → MCP 工具 ───────────────────

    def _handle_query_graph(self, graph_type: str = "code", **kwargs: Any) -> dict[str, Any]:
        """统一图谱查询——路由到 code/database/config 引擎。"""
        try:
            from orbit.graph.query import GraphQuery
            q = GraphQuery(code_graph=self._code_graph)
            return self._run_async(q.query(graph_type, **kwargs))  # type: ignore[arg-type]
        except Exception as e:
            return {"found": False, "error": str(e)}

    def _handle_detect_changes(self, base_ref: str = "HEAD~1", **_: Any) -> dict[str, Any]:
        """Git diff 变更影响分析。"""
        if not self._code_graph:
            return {"error": "CodeGraph 未初始化"}
        try:
            from orbit.graph.engines.change_detector import ChangeDetector
            detector = ChangeDetector(self._code_graph)
            impacts = self._run_async(detector.analyze(base_ref))
            return {"base_ref": base_ref, "impacts": [
                {"name": i.name, "file": i.file_path, "risk": i.risk,
                 "callers": i.callers[:5], "callees": i.callees[:5]}
                for i in impacts
            ]}
        except Exception as e:
            return {"error": str(e)}

    def _handle_export_artifact(self, output_path: str = ".orbit/graph/graph.db.zst", **_: Any) -> dict[str, Any]:
        """导出 zstd 压缩图谱产物。"""
        try:
            from pathlib import Path as _Path
            from orbit.graph.artifact import export_graph_artifact
            # P1-2 fix: 从 settings 或默认位置获取实际 DB 路径
            try:
                from orbit.core.config import settings as _s
                db_url = str(getattr(_s, "DATABASE_URL", "sqlite+aiosqlite:///data/graph.db"))
                if "///" in db_url:
                    db_path = db_url.rsplit("///", 1)[-1]
                else:
                    db_path = "data/graph.db"
            except Exception:
                db_path = "data/graph.db"
            ok = export_graph_artifact(db_path, output_path)
            return {"success": ok, "output": output_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_okf_import(self, bundle_dir: str = "", **_: Any) -> dict[str, Any]:
        """从 OKF bundle 导入领域知识。"""
        if not bundle_dir.strip():
            return {"success": False, "error": "bundle_dir is required"}
        try:
            from orbit.knowledge.okf_importer import OkfImporter
            importer = OkfImporter(self._engine)
            count = importer.import_bundle(bundle_dir)
            return {"success": True, "imported": count, "bundle_dir": bundle_dir}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_okf_export(self, output_dir: str = ".orbit/knowledge", **_: Any) -> dict[str, Any]:
        """导出知识图谱为 OKF bundle。"""
        try:
            from orbit.knowledge.okf_exporter import OkfExporter
            exporter = OkfExporter(self._engine)
            count = exporter.export(output_dir)
            exporter.generate_index(output_dir)
            exporter.generate_log(output_dir)
            return {"success": True, "exported": count, "output_dir": output_dir}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── JSON-RPC 请求处理 ──────────────────────────────────

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
