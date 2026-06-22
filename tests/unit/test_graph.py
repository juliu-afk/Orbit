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
        """validate() 也检测循环。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A"), make_node("B")],
            edges=[("A", "B"), ("B", "A")],
        )
        with pytest.raises(ValueError):
            graph.validate()

    def test_validate_missing_node(self):
        """边引用不存在的节点。"""
        graph = TaskGraph(
            task_id="t1",
            nodes=[make_node("A")],
            edges=[("A", "Z")],
        )
        with pytest.raises(ValueError, match="not in nodes"):
            graph.validate()

    def test_empty_dag(self):
        """空 DAG 正常。"""
        graph = TaskGraph(task_id="t1", nodes=[], edges=[])
        graph.validate()
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
