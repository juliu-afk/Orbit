"""causal/ 模块单元测试——CausalGraph domain DAG 构建 (networkx only, 无需 DoWhy)."""

import pytest

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")


class TestCausalModelManagerDAG:
    """测试 build_dag()——领域知识 DAG 构建."""

    def test_build_dag_structure(self, tmp_path):
        import sqlite3
        from orbit.causal.graph import CausalModelManager, VARIABLE_MAP, DOMAIN_DAG

        # 用临时 SQLite 数据库
        db_path = str(tmp_path / "test.db")
        db = sqlite3.connect(db_path)
        mgr = CausalModelManager(db=db)

        dag = mgr.build_dag()
        assert dag is not None

        # 验证节点——所有因果变量都在 DAG 中
        for var in VARIABLE_MAP:
            assert var in dag.nodes(), f"Variable {var} missing from DAG"

        # 验证边
        for src, tgt in DOMAIN_DAG:
            assert dag.has_edge(src, tgt), f"Edge {src}→{tgt} missing"

    def test_dag_is_acyclic(self, tmp_path):
        import sqlite3
        from orbit.causal.graph import CausalModelManager

        db_path = str(tmp_path / "test.db")
        db = sqlite3.connect(db_path)
        mgr = CausalModelManager(db=db)

        dag = mgr.build_dag()
        assert nx.is_directed_acyclic_graph(dag), "Domain DAG has a cycle"

    def test_dag_cycle_handling(self, tmp_path, monkeypatch):
        """如果领域 DAG 出现环（编辑错误），build_dag 应移除环边."""
        import sqlite3
        from orbit.causal.graph import CausalModelManager, DOMAIN_DAG

        db_path = str(tmp_path / "test.db")
        db = sqlite3.connect(db_path)
        mgr = CausalModelManager(db=db)

        # 临时注入一条会成环的边来测试环处理
        original_edges = list(DOMAIN_DAG)
        # 加反向边——agent_role → task_outcome 已存在，加 task_outcome → agent_role 成环
        DOMAIN_DAG.append(("task_outcome", "agent_role"))
        try:
            dag = mgr.build_dag()
            assert nx.is_directed_acyclic_graph(dag), "Should have removed cycle edge"
        finally:
            DOMAIN_DAG[:] = original_edges

    def test_last_graph_initial_none(self, tmp_path):
        import sqlite3
        from orbit.causal.graph import CausalModelManager

        db = sqlite3.connect(str(tmp_path / "test.db"))
        mgr = CausalModelManager(db=db)
        assert mgr.last_graph is None
        assert mgr.gcm_model is None
