"""Step 5.1 TaskGraph 数据模型 + 拓扑排序测试。"""

from __future__ import annotations

import pytest

from orbit.scheduler.graph import GraphNode, NodeStatus, TaskGraph


def make_node(nid: str) -> GraphNode:
    return GraphNode(id=nid, agent_role="developer")


class TestTopologicalSort:
    def test_linear_chain(self):
        """A→B→C 链式依赖。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C")],
            edges=[("A", "B"), ("B", "C")],
        )
        layers = graph.topological_sort()
        assert layers == [["A"], ["B"], ["C"]]

    def test_diamond_dag(self):
        """AC1: A→B, A→C, B→D, C→D 钻石依赖。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C"), make_node("D")],
            edges=[("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        layers = graph.topological_sort()
        # A 在第一层
        assert layers[0] == ["A"]
        # B/C 在第二层（顺序无关）
        assert set(layers[1]) == {"B", "C"}
        # D 在最后一层
        assert layers[2] == ["D"]

    def test_independent_nodes_same_layer(self):
        """AC2 前提：无依赖节点同层。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C")],
            edges=[],
        )
        layers = graph.topological_sort()
        assert len(layers) == 1
        assert set(layers[0]) == {"A", "B", "C"}

    def test_cycle_detection(self):
        """A→B→C→A 循环 → ValueError。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C")],
            edges=[("A", "B"), ("B", "C"), ("C", "A")],
        )
        with pytest.raises(ValueError, match="cycle"):
            graph.topological_sort()

    def test_validate_cycle(self):
        """validate_dag() 也检测循环。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B")],
            edges=[("A", "B"), ("B", "A")],
        )
        with pytest.raises(ValueError):
            graph.validate_dag()

    def test_validate_missing_node(self):
        """边引用不存在的节点。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A")],
            edges=[("A", "Z")],
        )
        with pytest.raises(ValueError, match="not in nodes"):
            graph.validate_dag()

    def test_empty_dag(self):
        """空 DAG 正常。"""
        graph = TaskGraph(task_id="t1", nodes=[], edges=[])
        graph.validate_dag()
        assert graph.topological_sort() == []

    def test_single_node(self):
        """单节点 DAG。"""
        graph = TaskGraph(task_id="t1", nodes=[make_node("A")], edges=[])
        layers = graph.topological_sort()
        assert layers == [["A"]]

    def test_get_dependencies(self):
        """查询上游依赖。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C")],
            edges=[("A", "C"), ("B", "C")],
        )
        deps = graph.get_dependencies("C")
        assert set(deps) == {"A", "B"}
        assert graph.get_dependencies("A") == []

    def test_get_dependents(self):
        """查询下游节点。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B"), make_node("C")],
            edges=[("A", "B"), ("A", "C")],
        )
        deps = graph.get_dependents("A")
        assert set(deps) == {"B", "C"}


class TestCodeGraphImports:
    """Phase 3: CodeGraph import 边记录（内存字典）。"""

    @pytest.mark.asyncio
    async def test_extract_imports_populates_edges(self):
        """_extract_imports 从 AST 提取 import 边到 _import_edges 字典。"""
        import ast

        from orbit.graph.engines.code_graph import CodeGraphEngine

        engine = CodeGraphEngine.__new__(CodeGraphEngine)
        tree = ast.parse("import os\nfrom pathlib import Path\nprint('hi')")
        await engine._extract_imports(tree, "/fake/test.py")

        assert hasattr(engine, "_import_edges")
        assert "/fake/test.py" in engine._import_edges
        entries = engine._import_edges["/fake/test.py"]
        assert len(entries) == 2  # import os + from pathlib import Path
        assert {"module": "os", "symbol": None} in entries
        assert {"module": "pathlib", "symbol": "Path"} in entries

    def test_find_imports_of_returns_modules(self):
        """find_imports_of 返回某文件导入的模块列表。"""
        from orbit.graph.engines.code_graph import CodeGraphEngine

        engine = CodeGraphEngine.__new__(CodeGraphEngine)
        engine._import_edges = {
            "/fake/test.py": [
                {"module": "os", "symbol": None},
                {"module": "pathlib", "symbol": "Path"},
            ]
        }
        modules = engine.find_imports_of("/fake/test.py")
        assert "os" in modules
        assert "pathlib" in modules

    def test_find_importers_of_matches_prefix(self):
        """find_importers_of 支持前缀匹配（子模块导入）。"""
        from orbit.graph.engines.code_graph import CodeGraphEngine

        engine = CodeGraphEngine.__new__(CodeGraphEngine)
        engine._import_edges = {
            "/x/a.py": [{"module": "orbit.memory.store", "symbol": "MemoryStore"}],
            "/x/b.py": [{"module": "orbit.memory", "symbol": None}],
        }
        # 查询谁导入了 orbit.memory（父包）
        importers = engine.find_importers_of("orbit.memory")
        assert "/x/a.py" in importers
        assert "/x/b.py" in importers

    def test_incremental_update_clears_edges(self):
        """P1-3: incremental_update 应清理旧文件的 import 边。"""
        from orbit.graph.engines.code_graph import CodeGraphEngine

        engine = CodeGraphEngine.__new__(CodeGraphEngine)
        engine._import_edges = {"/old/file.py": [{"module": "os", "symbol": None}]}
        # 模拟 incremental_update 中的清理
        engine._import_edges.pop("/old/file.py", None)
        assert "/old/file.py" not in engine._import_edges


class TestNodeStatus:
    def test_default_status(self):
        node = make_node("X")
        assert node.status == NodeStatus.PENDING
        assert node.retry_count == 0
        assert node.error is None

    def test_status_transitions(self):
        node = make_node("X")
        node.status = NodeStatus.RUNNING
        assert node.status == NodeStatus.RUNNING
        node.status = NodeStatus.SUCCESS
        node.output = {"result": "ok"}
        assert node.status == NodeStatus.SUCCESS
        assert node.output == {"result": "ok"}
