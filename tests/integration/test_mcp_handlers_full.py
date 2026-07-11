from unittest.mock import MagicMock
import pytest, tempfile, os
from orbit.knowledge.mcp_server import McpServer

@pytest.fixture
def s(): return McpServer()

@pytest.fixture
def scg():
    cg = MagicMock()
    cg.find_definitions_with_positions.return_value = [{"file":"a.py","line":1}]
    cg.get_callers.return_value = ["c1"]
    cg.find_implementations.return_value = [{"file":"b.py"}]
    cg.get_type_hierarchy.return_value = {"superclasses":["Base"]}
    cg.replace_body.return_value = True
    cg.insert_after.return_value = True
    cg.find_call_chain.return_value = [1,2,3]
    return McpServer(code_graph=cg)

class TestHandlers:
    def test_query_exact(self,s): assert isinstance(s._handle_query_knowledge(domain="t",concept="t",mode="exact"),dict)
    def test_query_semantic(self,s): assert isinstance(s._handle_query_knowledge(mode="semantic",concept="t",domain="t"),dict)
    def test_find_symbol_no_cg(self,s): assert isinstance(s._handle_find_symbol(symbol="f"),dict)
    def test_find_refs_no_cg(self,s): assert isinstance(s._handle_find_referencing_symbols(symbol="f"),dict)
    def test_overview(self,s):
        d=tempfile.mkdtemp(); f=os.path.join(d,"t.py")
        with open(f,"w") as fh: fh.write("class A:\n def m(self):pass\ndef f():pass\n")
        s._workspace_dir=d; r=s._handle_get_symbols_overview(file_path="t.py"); assert len(r["symbols"])>=2
    def test_trace_path(self,scg): assert isinstance(scg._handle_trace_path(source="a",target="b"),dict)
    def test_architecture(self,s): assert isinstance(s._handle_get_architecture(),dict)
    def test_search_code(self,s): assert isinstance(s._handle_search_code(query="def t"),dict)
    def test_dead_code(self,s): assert isinstance(s._handle_dead_code(),dict)
    def test_implementations(self,scg): assert isinstance(scg._handle_find_implementations(symbol="I"),dict)
    def test_type_hierarchy(self,scg): assert isinstance(scg._handle_type_hierarchy(symbol="C"),dict)
    def test_query_graph(self,s): assert isinstance(s._handle_query_graph(type="code",symbol="t"),dict)
    def test_detect_changes(self,s): assert isinstance(s._handle_detect_changes(),dict)
    def test_export_artifact(self,s): assert isinstance(s._handle_export_artifact(format="json"),dict)
    def test_okf_import(self,s): assert isinstance(s._handle_okf_import(bundle_dir="."),dict)
    def test_okf_export(self,s): assert isinstance(s._handle_okf_export(domain="t"),dict)
    def test_replace_symbol(self,scg): assert isinstance(scg._handle_replace_symbol_body(symbol="f",new_body="pass"),dict)
    def test_insert_after(self,scg): assert isinstance(scg._handle_insert_after_symbol(symbol="f",code="pass"),dict)
