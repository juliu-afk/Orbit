"""批次C单元测试——时序/分离/互模拟/拜占庭."""

class TestL9Temporal:
    def test_empty_graph(self):
        from orbit.hallucination.l9_temporal import L9TemporalValidator
        labs = {"IDLE": {"task_completed"}}
        r = L9TemporalValidator().validate({"IDLE":[]}, labs, "IDLE")
        assert r.passed
    def test_safety_violation(self):
        from orbit.hallucination.l9_temporal import L9TemporalValidator
        g = {"IDLE":["EVIL"],"EVIL":[]}
        labs = {"IDLE":set(),"EVIL":{"budget_exhausted"}}
        r = L9TemporalValidator().validate(g, labs, "IDLE")
        assert not r.passed

class TestL10Separation:
    def test_clean_code(self):
        from orbit.hallucination.l10_separation import L10SeparationValidator
        r = L10SeparationValidator().validate("x = 1\ny = x + 2")
        assert r.passed
    def test_frame_violation(self):
        from orbit.hallucination.l10_separation import L10SeparationValidator
        r = L10SeparationValidator().validate("def f(a):\n a.x = 5")
        assert not r.passed
    def test_risky_alias(self):
        from orbit.hallucination.l10_separation import L10SeparationValidator
        r = L10SeparationValidator().validate("x = [1]\ny = x\ny.append(2)")
        assert not r.passed

class TestBisimulation:
    def test_empty(self):
        from orbit.agents.bisim import BisimulationChecker
        assert BisimulationChecker().bisimilarity_score({}, {}) == 0.0
    def test_identical(self):
        from orbit.agents.bisim import BisimulationChecker
        a = {"s1":{"read":"s2"},"s2":{}}
        assert BisimulationChecker().bisimilarity_score(a, a) > 0.9
    def test_replaceable(self):
        from orbit.agents.bisim import BisimulationChecker
        rep, _ = BisimulationChecker.is_replaceable(0.95, cost_a=10, cost_b=20)
        assert rep

class TestBFTGuard:
    def test_not_destructive(self):
        from orbit.goal.bft import BFTGuard
        ok, _ = BFTGuard(4).approve("read_file")
        assert ok
    def test_destructive_rejected(self):
        g = __import__('orbit.goal.bft', fromlist=['BFTGuard']).BFTGuard(4)
        ok, _ = g.approve("DROP something", [True, True, False, False])
        assert not ok
    def test_destructive_approved(self):
        g = __import__('orbit.goal.bft', fromlist=['BFTGuard']).BFTGuard(4)
        ok, _ = g.approve("DROP something", [True, True, True, False])
        assert ok
    def test_fault_tolerance(self):
        from orbit.goal.bft import BFTGuard
        assert BFTGuard(4).fault_tolerance == 1
        assert BFTGuard(7).fault_tolerance == 2
