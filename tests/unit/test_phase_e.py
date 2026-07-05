"""Phase E 单元测试——LLMDistiller/GRPOScorer/PromptInjector."""
from __future__ import annotations

from orbit.evolution.distill import DistillationEngine
from orbit.evolution.anchor import AnchorGuard
from orbit.evolution.grpo import GRPOScorer
from orbit.evolution.inject import PromptInjector


class TestGRPOScorer:
    def test_record_baseline(self):
        scorer = GRPOScorer()
        scorer.record_baseline("audit", True)
        scorer.record_baseline("audit", False)
        scorer.record_baseline("audit", True)
        assert sum(scorer._baselines["audit"]) == 2

    def test_record_trial(self):
        scorer = GRPOScorer()
        scorer.record_trial("p1", True)
        scorer.record_trial("p1", True)
        scorer.record_trial("p1", False)
        assert scorer._trials["p1"] == [True, True, False]

    def test_baseline_rate(self):
        scorer = GRPOScorer()
        scorer.record_baseline("audit", True)
        scorer.record_baseline("audit", False)
        assert scorer._baseline_rate("audit") == 0.5

    def test_baseline_rate_empty(self):
        scorer = GRPOScorer()
        assert scorer._baseline_rate("unknown") == 0.5

    def test_update_utilities_no_engine(self):
        scorer = GRPOScorer()
        scorer.record_baseline("audit", True)
        scorer.record_trial("p1", True)
        scorer.update_utilities("audit")  # no engine——不崩溃

    def test_get_stats(self):
        scorer = GRPOScorer()
        scorer.record_baseline("audit", True)
        scorer.record_trial("p1", True)
        scorer.record_trial("p1", True)
        scorer.record_trial("p1", True)
        scorer.update_utilities("audit")
        assert scorer.get_stats("p1") is None  # 无 engine 不会生成 stats


class TestPromptInjector:
    def test_inject_no_engine(self):
        injector = PromptInjector()
        result = injector.inject("base prompt", category="audit")
        assert result == "base prompt"

    def test_inject_with_engine_no_principles(self):
        engine = DistillationEngine(":memory:")
        injector = PromptInjector(engine=engine)
        result = injector.inject("base", category="audit")
        assert result == "base"  # 无原则时不注入

    def test_inject_with_engine_has_principles(self):
        engine = DistillationEngine(":memory:")
        p = engine._add_principle("When checking AR, verify cutoff dates first", source="t1", category="audit", initial_score=0.8)
        assert p is not None, f"Got {p}"
        injector = PromptInjector(engine=engine)
        result = injector.inject("base", category="audit", min_utility=0.7)
        assert "已验证的高效策略原则" in result

    def test_inject_counts(self):
        engine = DistillationEngine(":memory:")
        engine._add_principle("test principle one", source="t1", category="audit", initial_score=0.9)
        injector = PromptInjector(engine=engine)
        injector.inject("base", category="audit", min_utility=0.7)
        assert injector.total_injected > 0


class TestLLMDistiller:
    def test_build_summaries(self):
        from orbit.evolution.llm_distill import LLMDistiller
        distiller = LLMDistiller()
        traj = {
            "trajectory": {"goal": "audit AR", "final_outcome": "completed", "quality_score": 0.9},
            "steps": [{"action": "read_file"}, {"action": "grep"}, {"action": "write_file"}],
        }
        result = distiller._build_summaries([traj])
        assert "audit AR" in result
        assert "read_file" in result

    def test_distill_too_few(self):
        from orbit.evolution.llm_distill import LLMDistiller
        import asyncio
        distiller = LLMDistiller()
        result = asyncio.run(distiller.distill_batch([{"trajectory": {}}], "audit"))
        assert result == []  # < 3 trajectories

    def test_distill_no_llm(self):
        from orbit.evolution.llm_distill import LLMDistiller
        import asyncio
        distiller = LLMDistiller(llm=None)
        trajs = []
        for i in range(3):
            trajs.append({
                "trajectory": {"goal": f"task {i}", "final_outcome": "completed", "quality_score": 0.9},
                "steps": [{"action": "read_file"}],
            })
        result = asyncio.run(distiller.distill_batch(trajs, "audit"))
        assert result == []  # 无 LLM → 空
