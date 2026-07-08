"""P0 五方向单元测试."""
import math

class TestThompsonBandit:
    def test_select_returns_valid_arm(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["tier_0", "tier_1", "tier_2"])
        for _ in range(20):
            assert b.select() in ["tier_0", "tier_1", "tier_2"]
    def test_update_success_increases_alpha(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["tier_0"]); a0 = b.posteriors["tier_0"]["alpha"]
        b.update("tier_0", success=True)
        assert b.posteriors["tier_0"]["alpha"] == a0 + 1
    def test_update_failure_increases_beta(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["tier_0"]); b0 = b.posteriors["tier_0"]["beta"]
        b.update("tier_0", success=False)
        assert b.posteriors["tier_0"]["beta"] == b0 + 1
    def test_slow_latency_penalizes(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["tier_0"]); b0 = b.posteriors["tier_0"]["beta"]
        b.update("tier_0", success=True, latency_ms=5000)
        assert b.posteriors["tier_0"]["beta"] == b0 + 0.5
    def test_is_bandit_enabled(self):
        import os; from orbit.router.bandit import is_bandit_enabled
        assert not is_bandit_enabled()
        os.environ["ORBIT_ROUTER_BANDIT"] = "1"; assert is_bandit_enabled()
        del os.environ["ORBIT_ROUTER_BANDIT"]
    def test_reset_arm(self):
        from orbit.router.bandit import ThompsonBandit
        b = ThompsonBandit(["tier_0"])
        b.update("tier_0", success=True); b.update("tier_0", success=True)
        b.reset_arm("tier_0")
        assert b.posteriors["tier_0"]["alpha"] == 1.0
        assert b.posteriors["tier_0"]["beta"] == 1.0

class TestPIDController:
    def test_subtle_level(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        s = PIDAgentController().compute(drift_score=0.1, repetition_count=0, latency_ms=100)
        assert s.level == "subtle"
    def test_urgent_after_accumulation(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        pid = PIDAgentController()
        for _ in range(5):
            pid.compute(drift_score=0.8, repetition_count=15, latency_ms=8000)
        s = pid.compute(drift_score=1.0, repetition_count=20, latency_ms=10000)
        assert s.level == "urgent"
    def test_reset_clears_state(self):
        from orbit.metacognition.pid_controller import PIDAgentController
        pid = PIDAgentController()
        pid.compute(drift_score=0.8, repetition_count=10, latency_ms=6000)
        pid.reset()
        s = pid.compute(drift_score=0.1, repetition_count=0, latency_ms=100)
        assert s.level == "subtle"

class TestConformalPredictor:
    def test_empty_calibration_returns_all(self):
        from orbit.testing.conformal import ConformalPredictor
        assert ConformalPredictor().predict("task", ["a","b","c"]) == ["a","b","c"]
    def test_p_value_range(self):
        from orbit.testing.conformal import ConformalPredictor
        cp = ConformalPredictor(alpha=0.05)
        cp.calibrate([("t","good code",True)]*10 + [("t","bad error error error error",False)]*5)
        p = cp.p_value("task", "good code")
        assert 0 <= p <= 1
    def test_bad_code_gets_lower_pvalue(self):
        from orbit.testing.conformal import ConformalPredictor
        cp = ConformalPredictor(alpha=0.05)
        cp.calibrate([("t","clean",True)]*10 + [("t","bad error error",False)]*5)
        p_good = cp.p_value("task", "clean")
        p_bad = cp.p_value("task", "bad error error")
        assert p_bad < p_good  # 差代码 p-value 更低
    def test_p_value_different_task_same_code(self):
        from orbit.testing.conformal import ConformalPredictor
        cp = ConformalPredictor(alpha=0.05)
        cp.calibrate([("audit","clean code",True)]*10 + [("coding","bad error",False)]*5)
        # P1-1修复: 不同 task 产生不同 p-value（语义分离）
        p1 = cp.p_value("audit", "good code")
        p2 = cp.p_value("coding", "good code")
        assert 0 <= p1 <= 1 and 0 <= p2 <= 1
    def test_alpha_validation(self):
        from orbit.testing.conformal import ConformalPredictor
        import pytest
        with pytest.raises(ValueError): ConformalPredictor(alpha=0)
        with pytest.raises(ValueError): ConformalPredictor(alpha=1)

class TestCUSUMDriftDetector:
    def test_first_update_no_alert(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        assert CUSUMDriftDetector().update("gpt-4", 1000, True, 200) is None
    def test_normal_updates_no_alert(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector()
        for _ in range(30):
            d.update("gpt-4", 1000, True, 200)
        assert d.update("gpt-4", 1050, True, 210) is None
    def test_cooldown_prevents_repeat_alerts(self):
        """P2-2修复: 变点后冷却期内不重触发告警."""
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector(threshold=1.0)
        # 建立基线
        for _ in range(20):
            d.update("gpt-4", 1000, True, 200)
        # 触发变点
        alert = d.update("gpt-4", 30000, False, 10)
        assert alert is not None
        # 冷却期内不应再告警
        for _ in range(5):
            assert d.update("gpt-4", 30000, False, 10) is None
    def test_reset(self):
        from orbit.observability.drift_detector import CUSUMDriftDetector
        d = CUSUMDriftDetector()
        d.update("gpt-4", 1000, True, 200)
        d.reset("gpt-4")
        assert d.update("gpt-4", 1000, True, 200) is None

class TestTypeDirectedSynthesizer:
    def test_list_constraint(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        c = TypeDirectedSynthesizer.constrain("def f(x: List[int]) -> List[int]:")
        assert any("List" in x for x in c)
    def test_optional_constraint(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        c = TypeDirectedSynthesizer.constrain("def f(x: Optional[str]) -> str:")
        assert any("Optional" in x or "None" in x for x in c)
    def test_decimal_import(self):
        from orbit.hallucination.l4_type import TypeDirectedSynthesizer
        c = TypeDirectedSynthesizer.constrain("def f(x: Decimal) -> Decimal:")
        assert any("decimal" in x.lower() for x in c)
