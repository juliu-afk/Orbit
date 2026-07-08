"""causal/ 模块单元测试——数据模型 + 降级模式 (无需 DoWhy)."""

import time

import pytest

from orbit.causal.models import CauseCandidate, CausalEdge, CausalGraph, RootCause


class TestCausalEdge:
    def test_valid_edge(self):
        e = CausalEdge(source_var="agent_role", target_var="task_outcome",
                       causal_strength=0.72, confidence=0.85, sample_count=100)
        assert e.source_var == "agent_role"
        assert e.causal_strength == 0.72

    def test_strength_clamped(self):
        """Pydantic Field(ge=0, le=1) 拒绝越界值."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            CausalEdge(source_var="a", target_var="b", causal_strength=1.5)


class TestCausalGraph:
    def test_empty_graph(self):
        g = CausalGraph()
        assert g.variables == []
        assert g.edges == []
        assert g.sample_size == 0

    def test_with_edges(self):
        edges = [
            CausalEdge(source_var="agent_role", target_var="task_outcome",
                       causal_strength=0.72, confidence=0.85, sample_count=100),
            CausalEdge(source_var="model_tier", target_var="latency",
                       causal_strength=0.68, confidence=0.91, sample_count=100),
        ]
        g = CausalGraph(variables=["agent_role", "model_tier", "task_outcome", "latency"],
                        edges=edges, sample_size=100, fit_quality=0.85)
        assert len(g.edges) == 2
        assert g.fit_quality == 0.85


class TestRootCause:
    def test_empty(self):
        rc = RootCause(task_id="task-1")
        assert rc.task_id == "task-1"
        assert rc.causes == []
        assert rc.top_cause is None
        assert rc.confidence == 0.0

    def test_with_causes(self):
        c1 = CauseCandidate(variable="agent_role", anomaly_score=0.72)
        c2 = CauseCandidate(variable="model_tier", anomaly_score=0.15)
        rc = RootCause(
            task_id="task-1",
            causes=[c1, c2],
            top_cause=c1,
            confidence=0.85,
        )
        assert rc.top_cause.variable == "agent_role"
        assert len(rc.causes) == 2
        assert rc.confidence == 0.85

    def test_explanation_failed_flag(self):
        rc = RootCause(task_id="task-1", explanation_failed=True)
        assert rc.explanation_failed is True

    def test_stale_flag(self):
        rc = RootCause(task_id="task-1", stale=True,
                       missing_variables=["model_tier"])
        assert rc.stale is True
        assert "model_tier" in rc.missing_variables


class TestCauseCandidate:
    def test_basic(self):
        c = CauseCandidate(variable="agent_role", anomaly_score=0.72,
                           explanation="换 architect 可提升 23% 成功率",
                           counterfactual="若换 architect，成功率 +23%±5%")
        assert c.variable == "agent_role"
        assert c.anomaly_score == 0.72
        assert "architect" in c.explanation

    def test_defaults(self):
        c = CauseCandidate(variable="model_tier")
        assert c.anomaly_score == 0.0
        assert c.explanation == ""
        assert c.counterfactual == ""
