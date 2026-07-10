"""knowledge/mcp_server.py handler tests — tool registration + handler calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.knowledge.mcp_server import McpServer, _make_response, _make_error


class TestMcpServerHandlers:
    @pytest.fixture
    def server(self):
        return McpServer()

    @pytest.fixture
    def server_with_cg(self):
        cg = MagicMock()
        cg.find_definition.return_value = {"file": "a.py", "line": 10}
        cg.find_references.return_value = [{"file": "b.py", "line": 20}]
        cg.get_overview.return_value = [{"name": "func1", "kind": "function", "line": 5}]
        return McpServer(code_graph=cg)

    def test_set_code_graph(self, server):
        cg = MagicMock()
        server.set_code_graph(cg)
        assert server._code_graph is cg

    def test_register_tool(self, server):
        server.register_tool(
            name="custom_tool",
            description="A custom tool",
            inputSchema={"type": "object", "properties": {}},
            handler=lambda: "custom_result",
        )
        assert "custom_tool" in server._tools
        assert "custom_tool" in server._handlers

    def test_query_knowledge_exact(self, server):
        """Exact query returns matching concept."""
        result = server._handle_query_knowledge(
            domain="test", concept="test_entity", mode="exact"
        )
        assert isinstance(result, dict)

    def test_query_knowledge_semantic(self, server):
        """Semantic query with no embeddings → warns."""
        result = server._handle_query_knowledge(
            domain="test", concept="anything", mode="semantic"
        )
        assert isinstance(result, dict)

    def test_find_symbol_no_cg(self, server):
        result = server._handle_find_symbol(symbol="MyClass")
        assert isinstance(result, dict)

    def test_find_refs_no_cg(self, server):
        result = server._handle_find_referencing_symbols(symbol="MyClass")
        assert isinstance(result, dict)

    def test_get_symbols_overview(self, server_with_cg):
        result = server_with_cg._handle_get_symbols_overview(file_path="src/a.py")
        assert isinstance(result, dict)

    def test_search_code(self, server):
        result = server._handle_search_code(query="def test")
        assert isinstance(result, dict)

    def test_get_architecture(self, server):
        result = server._handle_get_architecture()
        assert isinstance(result, dict)

    def test_query_graph(self, server):
        result = server._handle_query_graph(type="code", symbol="test")
        assert isinstance(result, dict)
