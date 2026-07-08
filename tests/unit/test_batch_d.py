"""批次D单元测试——Shapley/MDL/DP/TDA/自由能/信息几何/效应."""

class TestShapley:
    def test_equal_agents(self):
        from orbit.observability.attribution import ShapleyAttribution
        def v(s): return len(s) * 10.0
        vals = ShapleyAttribution.attribute(["a","b","c"], v)
        assert abs(vals["a"] - vals["b"]) < 0.01
    def test_mc_sample(self):
        from orbit.observability.attribution import ShapleyAttribution
        def v(s): return len(s) * 10.0
        vals = ShapleyAttribution.attribute(["a","b","c","d"], v, method="mc")
        assert abs(vals["a"] - vals["b"]) < 5  # MC近似容差

class TestMDL:
    def test_code_complexity(self):
        from orbit.review.mdl_scorer import MDLScorer
        assert MDLScorer.code_complexity("x = 1") > 0
    def test_pareto_frontier(self):
        from orbit.review.mdl_scorer import MDLScorer
        cands = [{"failures":0,"mdl":100},{"failures":1,"mdl":200},{"failures":2,"mdl":50}]
        fronts = MDLScorer.pareto_frontier(cands)
        assert len(fronts) >= 1

class TestDP:
    def test_laplace_no_crash(self):
        from orbit.observability.dp import DPGuard
        for _ in range(100):
            noisy = DPGuard(epsilon=1.0).laplace_mech(100.0)
            assert isinstance(noisy, float)  # P0修复: 不再崩溃

class TestTDA:
    def test_barcode(self):
        from orbit.graph.tda import TDAAnalyzer
        adj = [[0,1,2],[1,0,3],[2,3,0]]
        bc = TDAAnalyzer().persistence_barcode(adj)
        assert 0 in bc and 1 in bc

class TestFreeEnergy:
    def test_compute(self):
        from orbit.metacognition.free_energy import FreeEnergyMonitor
        F = FreeEnergyMonitor().compute(0.3, 0.2, 0.5)
        assert abs(F - (-0.27)) < 0.01
    def test_estimate(self):
        from orbit.metacognition.free_energy import FreeEnergyMonitor
        F = FreeEnergyMonitor.estimate_from_alerts(0.8, 10, 6000)
        assert F > 0.4

class TestInfoGeometry:
    def test_natural_gradient(self):
        from orbit.evolution.info_geom import InfoGeometry
        ng = InfoGeometry.natural_gradient([1.0, 0.5], [2.0, 1.0])
        assert len(ng) == 2

class TestEffectTracker:
    def test_pure(self):
        from orbit.hallucination.effect_tracker import EffectTracker
        e = EffectTracker.track("def f(x):\n return x + 1")
        assert "f" in e and "pure" in e["f"]
    def test_async(self):
        from orbit.hallucination.effect_tracker import EffectTracker
        e = EffectTracker.track("async def f():\n await g()")
        assert "f" in e and "async" in e["f"]
