"""批次D单元测试——Shapley/MDL/DP/TDA/自由能/信息几何/效应."""

class TestShapley:
    def test_equal_agents(self):
        from orbit.observability.attribution import ShapleyAttribution
        def v(s): return len(s) * 10.0
        vals = ShapleyAttribution.attribute(["a","b","c"], v)
        assert abs(vals["a"] - vals["b"]) < 0.01

class TestMDL:
    def test_code_complexity(self):
        from orbit.review.mdl_scorer import MDLScorer
        c = MDLScorer.code_complexity("x = 1")
        assert c > 0

class TestDP:
    def test_laplace(self):
        from orbit.observability.dp import DPGuard
        noisy = DPGuard(epsilon=1.0).laplace_mech(100.0)
        assert abs(noisy - 100.0) < 20  # 大概率在±20内

class TestTDA:
    def test_barcode(self):
        from orbit.graph.tda import TDAAnalyzer
        adj = [[0,1,2],[1,0,1.5],[2,1.5,0]]
        bc = TDAAnalyzer().persistence_barcode(adj)
        assert 0 in bc and 1 in bc

class TestFreeEnergy:
    def test_compute(self):
        from orbit.metacognition.free_energy import FreeEnergyMonitor
        F = FreeEnergyMonitor().compute(0.3, 0.2, 0.5)
        assert F == -0.3  # complexity - accuracy
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
        assert "async" in e.get("f", set())
