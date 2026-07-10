import sys
from unittest.mock import MagicMock
import pytest
from orbit.integration.wiring import OrbitWiring

_MODULES = ["orbit.observability.trajectory","orbit.memory.episodic","orbit.memory.profile",
"orbit.memory.agentic","orbit.evolution.distill","orbit.evolution.anchor","orbit.evolution.grpo",
"orbit.evolution.inject","orbit.evolution.llm_distill","orbit.metacognition.monitor",
"orbit.agents.mcts","orbit.router.bandit","orbit.observability.drift_detector",
"orbit.metacognition.pid_controller","orbit.testing.conformal","orbit.graph.spectral",
"orbit.compression.ib_compressor","orbit.context.ot_matcher","orbit.agents.mdp",
"orbit.hallucination.abstract_interp","orbit.compose.mechanism","orbit.evolution.pac_bounds",
"orbit.graph.engines.slicer","orbit.hallucination.l9_temporal","orbit.hallucination.l10_separation",
"orbit.agents.bisim","orbit.goal.bft","orbit.observability.attribution","orbit.review.mdl_scorer",
"orbit.observability.dp","orbit.graph.tda","orbit.metacognition.free_energy",
"orbit.evolution.info_geom","orbit.hallucination.effect_tracker","orbit.gateway.client"]

@pytest.fixture(autouse=True)
def _mock():
    saved = {}
    for m in _MODULES:
        mock = MagicMock()
        cls_name = m.split(".")[-1]
        cls_name = "".join(w.capitalize() for w in cls_name.split("_"))
        setattr(mock, cls_name, MagicMock())
        saved[m] = sys.modules.get(m)
        sys.modules[m] = mock
    yield
    for m, o in saved.items():
        if o is None: sys.modules.pop(m, None)
        else: sys.modules[m] = o

class TestAllGetters:
    @pytest.fixture
    def w(self): return OrbitWiring(db_path=":memory:")
    def test_traj(self,w): assert w._get_trajectory() is not None
    def test_epi(self,w): assert w._get_episodic() is not None
    def test_prof(self,w): assert w._get_profile() is not None
    def test_ag(self,w): assert w._get_agentic() is not None
    def test_dis(self,w): assert w._get_distill() is not None
    def test_anc(self,w): assert w._get_anchor() is not None
    def test_grpo(self,w): assert w._get_grpo() is not None
    def test_inj(self,w): assert w._get_injector() is not None
    def test_lld(self,w): assert w._get_llm_distill() is not None
    def test_mon(self,w): assert w._get_monitor() is not None
    def test_mcts(self,w): assert w._get_mcts() is not None
    def test_band(self,w): assert w._get_bandit() is not None
    def test_drift(self,w): assert w._get_drift() is not None
    def test_pid(self,w): assert w._get_pid() is not None
    def test_conf(self,w): assert w._get_conformal() is not None
    def test_spec(self,w): assert w._get_spectral() is not None
    def test_ib(self,w): assert w._get_ib() is not None
    def test_ot(self,w): assert w._get_ot() is not None
    def test_mdp(self,w): assert w._get_mdp() is not None
    def test_abs(self,w): assert w._get_abs_pipe() is not None
    def test_vcg(self,w): assert w._get_vcg() is not None
    def test_pac(self,w): assert w._get_pac() is not None
    def test_slice(self,w): assert w._get_slicer() is not None
    def test_temp(self,w): assert w._get_temporal() is not None
    def test_sep(self,w): assert w._get_sep() is not None
    def test_bisim(self,w): assert w._get_bisim() is not None
    def test_bft(self,w): assert w._get_bft() is not None
    def test_shap(self,w): assert w._get_shapley() is not None
    def test_mdl(self,w): assert w._get_mdl() is not None
    def test_dp(self,w): assert w._get_dp() is not None
    def test_tda(self,w): assert w._get_tda() is not None
    def test_fe(self,w): assert w._get_fe() is not None
    def test_ig(self,w): assert w._get_ig() is not None
    def test_eff(self,w): assert w._get_effect() is not None
    def test_llm(self,w): assert w._get_llm_client() is not None
    def test_cache(self,w): a=w._get_trajectory(); b=w._get_trajectory(); assert a is b
