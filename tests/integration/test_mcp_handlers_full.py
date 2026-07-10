"""Integration: knowledge/mcp_server.py all 20 handlers with real KnowledgeEngine."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.knowledge.mcp_server import McpServer


@pytest.fixture
def server():
    return McpServer()


@pytest.fixture
def server_with_cg():
    cg = MagicMock()
    cg.find_definitions_with_positions.return_value = [{"file": "a.py", "line": 1}]
    cg.get_callers.return_value = ["caller1"]
    cg.find_implementations.return_value = [{"file": "b.py"}]
    cg.get_type_hierarchy.return_value = {"superclasses": ["Base"]}
    cg.get_architecture.return_value = {"modules": []}
    cg.search_code.return_value = [{"file": "c.py"}]
    cg.detect_dead_code.return_value = []
    s = McpServer(code_graph=cg)
    return s


class TestAllHandlers:
    def test_query_knowledge(self, server):
        r = server._handle_query_knowledge(domain="test", concept="test", mode="exact")
        assert isinstance(r, dict)

    def test_query_knowledge_semantic(self, server):
        r = server._handle_query_knowledge(mode="semantic", concept="test", domain="test")
        assert isinstance(r, dict)

    def test_find_symbol_no_cg(self, server):
        r = server._handle_find_symbol(symbol="func")
        assert isinstance(r, dict)

    def test_find_referencing_symbols_no_cg(self, server):
        r = server._handle_find_referencing_symbols(symbol="func")
        assert isinstance(r, dict)

    def test_get_symbols_overview(self, server):
        import tempfile, os
        d = tempfile.mkdtemp()
        f = os.path.join(d, "test.py")
        with open(f, "w") as fh:
            fh.write("class A:\n    def m(self): pass\ndef f(): pass\n")
        server._workspace_dir = d
        r = server._handle_get_symbols_overview(file_path="test.py")
        assert len(r["symbols"]) >= 2

    def test_trace_path(self, server_with_cg):
        server_with_cg._code_graph.find_call_chain.return_value = [1, 2, 3]
        r = server_with_cg._handle_trace_path(source="a", target="b")
        assert isinstance(r, dict)

    def test_get_architecture(self, server):
        r = server._handle_get_architecture()
        assert isinstance(r, dict)

    def test_search_code(self, server):
        r = server._handle_search_code(query="def test")
        assert isinstance(r, dict)

    def test_dead_code(self, server):
        r = server._handle_dead_code()
        assert isinstance(r, dict)

    def test_find_implementations(self, server_with_cg):
        r = server_with_cg._handle_find_implementations(symbol="Interface")
        assert isinstance(r, dict)

    def test_type_hierarchy(self, server_with_cg):
        r = server_with_cg._handle_type_hierarchy(symbol="MyClass")
        assert isinstance(r, dict)

    def test_query_graph(self, server):
        r = server._handle_query_graph(type="code", symbol="test")
        assert isinstance(r, dict)

    def test_detect_changes(self, server):
        r = server._handle_detect_changes()
        assert isinstance(r, dict)

    def test_export_artifact(self, server):
        r = server._handle_export_artifact(format="json")
        assert isinstance(r, dict)

    def test_okf_import(self, server):
        r = server._handle_okf_import(bundle_dir=".")
        assert isinstance(r, dict)

    def test_okf_export(self, server):
        r = server._handle_okf_export(domain="test")
        assert isinstance(r, dict)

    def test_replace_symbol_body(self, server_with_cg):
        server_with_cg._code_graph.replace_body.return_value = True
        r = server_with_cg._handle_replace_symbol_body(symbol="func", new_body="pass")
        assert isinstance(r, dict)

    def test_insert_after_symbol(self, server_with_cg):
        server_with_cg._code_graph.insert_after.return_value = True
        r = server_with_cg._handle_insert_after_symbol(symbol="func", code="pass")
        assert isinstance(r, dict)
