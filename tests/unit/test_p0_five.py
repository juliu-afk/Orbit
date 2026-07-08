"""P0 五方向单元测试."""
class TestThompsonBandit:
    def test_select(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["t0","t1","t2"])
        for _ in range(20): assert b.select() in ["t0","t1","t2"]
    def test_success(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["t0"]); a0 = b.posteriors["t0"]["alpha"]
        b.update("t0", success=True); assert b.posteriors["t0"]["alpha"] == a0 + 1
    def test_failure(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["t0"]); b0 = b.posteriors["t0"]["beta"]
        b.update("t0", success=False); assert b.posteriors["t0"]["beta"] == b0 + 1
    def test_latency_penalty(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["t0"]); b0 = b.posteriors["t0"]["beta"]
        b.update("t0", True, 5000); assert b.posteriors["t0"]["beta"] == b0 + 0.5
    def test_enabled(self):
        import os; from orbit.router.bandit import is_bandit_enabled
        assert not is_bandit_enabled(); os.environ["ORBIT_ROUTER_BANDIT"]="1"
        assert is_bandit_enabled(); del os.environ["ORBIT_ROUTER_BANDIT"]
    def test_reset(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["t0"]); b.update("t0",True); b.update("t0",True)
        b.reset_arm("t0"); assert b.posteriors["t0"]["alpha"]==1.0 and b.posteriors["t0"]["beta"]==1.0

class TestPIDController:
    def test_subtle(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        assert PIDAgentController().compute(0.1,0,100).level=="subtle"
    def test_urgent(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        pid = PIDAgentController()
        for _ in range(5): pid.compute(0.8,15,8000)
        assert pid.compute(1.0,20,10000).level=="urgent"
    def test_reset(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        pid = PIDAgentController(); pid.compute(0.8,10,6000); pid.reset()
        assert pid.compute(0.1,0,100).level=="subtle"

class TestConformalPredictor:
    def test_empty(self):
        from orbit.testing.conformal import ConformalPredictor
        assert ConformalPredictor().predict("t",["a","b"])==["a","b"]
    def test_p_value_range(self):
        from orbit.testing.conformal import ConformalPredictor
        cp = ConformalPredictor(); cp.calibrate([("t","ok",True)]*10+[("t","bad error",False)]*5)
        p = cp.p_value("x","ok"); assert 0<=p<=1
    def test_alpha_validation(self):
        from orbit.testing.conformal import ConformalPredictor
        import pytest
        with pytest.raises(ValueError): ConformalPredictor(alpha=0)
        with pytest.raises(ValueError): ConformalPredictor(alpha=1)

class TestCUSUMDriftDetector:
    def test_first_no_alert(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        assert CUSUMDriftDetector().update("g",1000,True,200) is None
    def test_normal_no_alert(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector()
        for _ in range(30): d.update("g",1000,True,200)
        assert d.update("g",1050,True,210) is None
    def test_cooldown(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector(threshold=1.0)
        for _ in range(20): d.update("g",1000,True,200)
        assert d.update("g",30000,False,10) is not None
        for _ in range(5): assert d.update("g",30000,False,10) is None
    def test_reset(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector(); d.update("g",1000,True,200); d.reset("g")
        assert d.update("g",1000,True,200) is None

class TestTypeDirectedSynthesizer:
    def test_list(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        assert any("List" in x for x in TypeDirectedSynthesizer.constrain("def f(x: List[int]) -> List[int]:"))
    def test_optional(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        assert any("Optional" in x or "None" in x for x in TypeDirectedSynthesizer.constrain("def f(x: Optional[str]) -> str:"))
    def test_decimal(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        assert any("decimal" in x.lower() for x in TypeDirectedSynthesizer.constrain("def f(x: Decimal) -> Decimal:"))
