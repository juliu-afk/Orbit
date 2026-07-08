"""批次A单元测试——频谱/博弈/PAC/切片."""
import math

class TestSpectralAnalyzer:
    def test_empty(self):
        from orbit.graph.spectral import SpectralAnalyzer, SpectralReport
        r = SpectralAnalyzer().analyze.__wrapped__ if hasattr(SpectralAnalyzer().analyze, '__wrapped__') else None
        r = SpectralAnalyzer().analyze
        # 空矩阵测试——需要scipy
        try:
            import scipy.sparse as sp
            adj = sp.csr_matrix((3,3))
            report = SpectralAnalyzer().analyze(adj)
            assert isinstance(report, SpectralReport)
        except ImportError:
            import pytest; pytest.skip("no scipy")
    def test_report_defaults(self):
        from orbit.graph.spectral import SpectralReport
        r = SpectralReport()
        assert r.algebraic_connectivity == 0.0

class TestVCGAllocator:
    def test_empty(self):
        from orbit.compose.mechanism import VCGAllocator
        assert VCGAllocator().allocate([], []) == []
    def test_single_assignment(self):
        from orbit.compose.mechanism import VCGAllocator, AgentBid
        tasks = [{"id":"t1","description":"test"}]
        bids = [AgentBid("a1","t1",cost=5,capability=0.9)]
        result = VCGAllocator().allocate(tasks, bids)
        assert len(result) == 1 and result[0].agent_name == "a1"
    def test_best_wins(self):
        from orbit.compose.mechanism import VCGAllocator, AgentBid
        tasks = [{"id":"t1","description":"test"}]
        bids = [AgentBid("a1","t1",5,0.5), AgentBid("a2","t1",1,0.9)]
        result = VCGAllocator().allocate(tasks, bids)
        assert result[0].agent_name == "a2"

class TestPACBound:
    def test_compute(self):
        from orbit.evolution.pac_bounds import PACBound
        eps = PACBound().compute(H_size=100, m_samples=100)
        assert 0 < eps < 1
    def test_more_samples_tighter(self):
        from orbit.evolution.pac_bounds import PACBound
        pb = PACBound()
        assert pb.compute(100, 500) < pb.compute(100, 50)
    def test_adaptive_threshold(self):
        from orbit.evolution.pac_bounds import PACBound
        pb = PACBound()
        t = pb.adaptive_threshold(50, 10)  # 10 samples, 50 principles → wide bound
        assert t > 3  # should increase threshold
        t2 = pb.adaptive_threshold(10, 500)  # many samples → tight bound
        assert t2 <= 3

class TestProgramSlicer:
    def test_forward_slice(self):
        from orbit.graph.engines.slicer import ProgramSlicer
        code = "x = 1\ny = x + 2\nz = y * 3\nprint(z)"
        lines = ProgramSlicer().forward_slice(code, 1, "x")
        assert 2 in lines  # line 2 uses x
    def test_backward_slice(self):
        from orbit.graph.engines.slicer import ProgramSlicer
        code = "x = 1\ny = x + 2\nz = y * 3\nprint(z)"
        lines = ProgramSlicer().backward_slice(code, 4)  # print(z) depends on z
        assert 3 in lines  # z defined on line 3
    def test_syntax_error(self):
        from orbit.graph.engines.slicer import ProgramSlicer
        assert ProgramSlicer().forward_slice("def broken:", 1, "x") == set()
