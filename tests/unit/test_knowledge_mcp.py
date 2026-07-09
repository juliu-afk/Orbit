"""Step 3.4d McpServer 单元测试 + Phase 1 图谱工具 + OKF 导出器。"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from orbit.knowledge.engine import KnowledgeEngine
from orbit.knowledge.mcp_server import McpServer, _make_error, _make_response
from orbit.knowledge.store import KnowledgeStore


class TestMcpServer:
    """MCP JSON-RPC 协议——工具列表/调用/错误处理。"""

    @pytest.fixture
    def server(self) -> Generator[McpServer, None, None]:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        engine = KnowledgeEngine(store=store)
        s = McpServer(engine=engine)
        yield s
        store.close(cleanup=True)

    def _request(
        self,
        server: McpServer,
        method: str,
        params: dict[str, Any] | None = None,
        req_id: int = 1,
    ) -> Any:
        raw = server._handle_request(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
        )
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
        resp = self._request(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {"domain": "accounting", "concept": "ROE", "mode": "exact"},
            },
        )
        content = resp["result"]["content"][0]["text"]
        data = json.loads(content)
        assert data["found"] is True
        assert "净资产收益率" in data["content"]

    def test_tools_call_not_found(self, server: McpServer) -> None:
        """不存在的概念返回 found=False。"""
        resp = self._request(
            server,
            "tools/call",
            {
                "name": "query_knowledge",
                "arguments": {"concept": "NonExistent"},
            },
        )
        content = resp["result"]["content"][0]["text"]
        data = json.loads(content)
        assert data["found"] is False

    def test_tools_call_unknown_tool(self, server: McpServer) -> None:
        """调用未注册工具返回错误。"""
        resp = self._request(
            server,
            "tools/call",
            {
                "name": "unknown_tool",
                "arguments": {},
            },
            req_id=2,
        )
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
        raw = server._handle_request(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
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


# ── Phase 1 mock 数据与辅助函数 ────────────────────────────

_MOCK_NODES = [
    {"id": "n1", "name": "main", "type": "function", "file_path": "main.py",
     "start_line": 1, "end_line": 10, "meta": {"namespace": "__main__"}},
    {"id": "n2", "name": "handleRequest", "type": "function", "file_path": "api.py",
     "start_line": 5, "end_line": 20, "meta": {"namespace": "api"}},
    {"id": "n3", "name": "ProcessOrder", "type": "function", "file_path": "services.py",
     "start_line": 10, "end_line": 30, "meta": {"namespace": "services"}},
    {"id": "n4", "name": "BaseHandler", "type": "class", "file_path": "base.py",
     "start_line": 1, "end_line": 15, "meta": {"namespace": "base"}},
    {"id": "n5", "name": "ConcreteHandler", "type": "class", "file_path": "impl.py",
     "start_line": 1, "end_line": 25, "meta": {"namespace": "impl"}},
    {"id": "n6", "name": "orphan_func", "type": "function", "file_path": "unused.py",
     "start_line": 1, "end_line": 5, "meta": {"namespace": "unused"}},
]
_MOCK_EDGES = [
    {"id": "e1", "source_id": "n1", "target_id": "n2", "edge_type": "calls"},
    {"id": "e2", "source_id": "n2", "target_id": "n3", "edge_type": "calls"},
    {"id": "e3", "source_id": "n5", "target_id": "n4", "edge_type": "inherits"},
]


def _make_mock_code_graph():
    """构建 mock CodeGraphEngine——所有方法返回预设数据。"""
    cg = MagicMock()
    cg.get_all_nodes = MagicMock(return_value=_MOCK_NODES)
    cg.get_all_edges = MagicMock(return_value=_MOCK_EDGES)
    cg.get_callers = MagicMock(return_value=["main"])
    cg.get_callees = MagicMock(return_value=["ProcessOrder"])

    def _find_defs(symbol: str):
        return [{"file_path": "services.py", "start_line": 10, "end_line": 30, "name": "ProcessOrder"}] if symbol == "ProcessOrder" else []
    cg.find_definitions_with_positions = MagicMock(side_effect=_find_defs)
    cg.incremental_update = MagicMock(return_value=True)
    return cg


def _install_mock_graph(server: McpServer, code_graph=None):
    """注入 mock 代码图谱 + 拦截 _run_async 为直通。

    WHY set_code_graph: 内部调 _register_code_tools()——9 新工具必须走此路径。
    WHY _run_async = lambda x: x: handler 已将 async 方法调用的返回值传入，
    直通即可——mock 方法直接返回数据而非协程。
    """
    server.set_code_graph(code_graph or _make_mock_code_graph())
    server._run_async = lambda x: x


# ── Phase 1 查询工具测试 ────────────────────────────────────

class TestGraphQueryTools:
    """trace_path / get_architecture / search_code / dead_code / find_implementations。"""

    @pytest.fixture
    def server(self) -> Generator[McpServer, None, None]:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        s = McpServer(engine=KnowledgeEngine(store=store))
        _install_mock_graph(s)
        yield s
        store.close(cleanup=True)

    def _call(self, server: McpServer, tool: str, args: dict | None = None) -> Any:
        raw = server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": tool, "arguments": args or {}}})
        assert raw is not None
        return json.loads(json.loads(raw)["result"]["content"][0]["text"])

    def test_tools_list_includes_new(self, server: McpServer) -> None:
        raw = server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in json.loads(raw)["result"]["tools"]]
        for tool in ("trace_path", "get_architecture", "search_code", "dead_code",
                      "find_implementations", "replace_symbol_body", "safe_delete_symbol"):
            assert tool in names, f"Missing tool: {tool}"

    def test_trace_path_both_directions(self, server: McpServer) -> None:
        result = self._call(server, "trace_path", {"symbol": "ProcessOrder", "direction": "both", "max_depth": 2})
        assert "callers" in result and "callees" in result

    def test_trace_path_in_only(self, server: McpServer) -> None:
        result = self._call(server, "trace_path", {"symbol": "ProcessOrder", "direction": "in", "max_depth": 1})
        assert len(result["callees"]) == 0

    def test_trace_path_no_code_graph(self, server: McpServer) -> None:
        server._code_graph = None
        result = self._call(server, "trace_path", {"symbol": "foo"})
        assert "error" in result

    def test_get_architecture_stats(self, server: McpServer) -> None:
        result = self._call(server, "get_architecture", {})
        for key in ("languages", "module_count", "entry_points", "hotspots", "node_count", "edge_count"):
            assert key in result, f"Missing key: {key}"
        assert "py" in result["languages"]

    def test_dead_code_finds_orphan(self, server: McpServer) -> None:
        result = self._call(server, "dead_code", {})
        names = [f["name"] for f in result["dead_functions"]]
        assert "orphan_func" in names

    def test_find_implementations_finds_subclass(self, server: McpServer) -> None:
        result = self._call(server, "find_implementations", {"class_name": "BaseHandler"})
        assert result["found"] is True
        assert "ConcreteHandler" in [i["name"] for i in result["implementations"]]

    def test_find_implementations_not_found(self, server: McpServer) -> None:
        result = self._call(server, "find_implementations", {"class_name": "NoSuchClass"})
        assert result["found"] is False


# ── Phase 1 编辑工具测试 ────────────────────────────────────

class TestSemanticEditTools:
    """replace_symbol_body / insert_after / insert_before / safe_delete。"""

    @pytest.fixture
    def server(self) -> Generator[McpServer, None, None]:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        s = McpServer(engine=KnowledgeEngine(store=store))
        _install_mock_graph(s)
        tmp = tempfile.mkdtemp()
        s._workspace_dir = tmp
        (Path(tmp) / "services.py").write_text(
            "def ProcessOrder():\n    # 旧实现\n    result = do_something()\n    return result\n",
            encoding="utf-8",
        )
        yield s
        store.close(cleanup=True)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def _call(self, server: McpServer, tool: str, args: dict | None = None) -> Any:
        raw = server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": tool, "arguments": args or {}}})
        assert raw is not None
        return json.loads(json.loads(raw)["result"]["content"][0]["text"])

    def test_replace_symbol_body_success(self, server: McpServer) -> None:
        result = self._call(server, "replace_symbol_body", {"symbol": "ProcessOrder", "new_body": "return 42"})
        assert result["success"] is True
        content = (Path(server._workspace_dir) / "services.py").read_text(encoding="utf-8")
        assert "return 42" in content

    def test_insert_after_symbol_success(self, server: McpServer) -> None:
        result = self._call(server, "insert_after_symbol", {"symbol": "ProcessOrder", "code": "def new_func():\n    pass"})
        assert result["success"] is True
        assert "def new_func" in (Path(server._workspace_dir) / "services.py").read_text(encoding="utf-8")

    def test_insert_before_symbol_success(self, server: McpServer) -> None:
        result = self._call(server, "insert_before_symbol", {"symbol": "ProcessOrder", "code": "# comment"})
        assert result["success"] is True
        assert "# comment" in (Path(server._workspace_dir) / "services.py").read_text(encoding="utf-8")

    def test_safe_delete_refuses_with_callers(self, server: McpServer) -> None:
        result = self._call(server, "safe_delete_symbol", {"symbol": "ProcessOrder"})
        assert result["success"] is False and "调用者" in result["error"]

    def test_edit_tool_symbol_not_found(self, server: McpServer) -> None:
        result = self._call(server, "replace_symbol_body", {"symbol": "NonExistent", "new_body": "pass"})
        assert result["success"] is False


# ── Phase 1 OKF 导出器测试 ──────────────────────────────────

class TestOkfExporter:
    """okf_exporter.py——OKF v0.1 导出。"""

    def test_export_creates_bundle(self) -> None:
        from orbit.knowledge.okf_exporter import OkfExporter
        store = KnowledgeStore(db_path=Path(tempfile.mktemp(suffix=".db")))
        store.initialize()
        engine = KnowledgeEngine(store=store)
        with tempfile.TemporaryDirectory() as tmp:
            exporter = OkfExporter(engine)
            count = exporter.export(tmp)
            exporter.generate_index(tmp)
            exporter.generate_log(tmp)
            assert count >= 1
            assert (Path(tmp) / "index.md").exists()
            assert (Path(tmp) / "log.md").exists()
            assert sum(1 for _ in Path(tmp).iterdir() if _.is_dir()) >= 1
        store.close(cleanup=True)

    def test_export_concept_has_frontmatter(self) -> None:
        from orbit.knowledge.okf_exporter import OkfExporter
        store = KnowledgeStore(db_path=Path(tempfile.mktemp(suffix=".db")))
        store.initialize()
        engine = KnowledgeEngine(store=store)
        with tempfile.TemporaryDirectory() as tmp:
            OkfExporter(engine).export(tmp)
            concept_files = [f for f in Path(tmp).rglob("*.md") if f.name not in ("index.md", "log.md")]
            assert len(concept_files) >= 1
            content = concept_files[0].read_text(encoding="utf-8")
            assert content.startswith("---") and "type:" in content
        store.close(cleanup=True)

    def test_export_empty_store_handles_gracefully(self) -> None:
        from orbit.knowledge.okf_exporter import OkfExporter
        store = KnowledgeStore(db_path=Path(tempfile.mktemp(suffix=".db")))
        store.initialize()
        conn = store._get_conn()
        conn.execute("DELETE FROM knowledge_concepts")
        conn.commit()
        engine = KnowledgeEngine()
        engine._store = store  # 避免 initialize() 重新插入种子数据
        with tempfile.TemporaryDirectory() as tmp:
            assert OkfExporter(engine).export(tmp) == 0
        store.close(cleanup=True)
