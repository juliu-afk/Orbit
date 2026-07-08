"""批次B单元测试——IB/OT/MDP/抽象解释."""

class TestIBCompressor:
    def test_compress_empty(self):
        from orbit.compression.ib_compressor import IBCompressor
        assert IBCompressor().compress([], 1000) == []
    def test_compress_knapsack(self):
        from orbit.compression.ib_compressor import IBCompressor
        frags = [{"text":"a","tokens":300,"mi_score":0.8},
                 {"text":"b","tokens":200,"mi_score":0.5},
                 {"text":"c","tokens":100,"mi_score":0.3}]
        result = IBCompressor().compress(frags, 400)
        assert len(result) >= 1
    def test_cluster(self):
        from orbit.compression.ib_compressor import IBCompressor
        frags = [{"text":str(i),"tokens":100,"mi_score":i/10} for i in range(10)]
        result = IBCompressor(n_clusters=3).cluster(frags)
        assert len(result) == 3

class TestOTMatcher:
    def test_empty(self):
        from orbit.context.ot_matcher import OTMatcher
        assert OTMatcher().match([], []) == []
    def test_basic_match(self):
        from orbit.context.ot_matcher import OTMatcher
        ctx = [[1.0,0.0],[0.0,1.0]]
        needs = [[1.0,0.0]]
        result = OTMatcher(reg=0.5).match(ctx, needs)
        assert result[0][1] == 0  # ctx[0] matched to need[0]

class TestAgentMDP:
    def test_state_features(self):
        from orbit.agents.mdp import AgentMDP
        f = AgentMDP().state_features({"file_count":5,"risk":"medium","tool_calls":10})
        assert len(f) == 5
    def test_bellman_gap(self):
        from orbit.agents.mdp import AgentMDP
        t = [{"s":[0.2,0.5,0.3,0.1,0.0],"a":"call_tool","r":-0.2,
              "s_next":[0.2,0.5,0.4,0.2,0.0]}]
        gap = AgentMDP().compute_bellman_gap(t)
        assert gap >= 0

class TestAbstractPipeline:
    def test_analyze(self):
        from orbit.hallucination.abstract_interp import AbstractPipelineAnalyzer
        deps = AbstractPipelineAnalyzer.analyze_dependencies(["L1","L4","L7"])
        assert "L1" in deps and deps["L1"]["affects"] == ["L4","L7"]
    def test_skip_recommendation(self):
        from orbit.hallucination.abstract_interp import AbstractPipelineAnalyzer
        skip = AbstractPipelineAnalyzer.skip_recommendation("L1", ["L1","L4","L7","L5"])
        assert "L4" in skip and "L7" in skip
