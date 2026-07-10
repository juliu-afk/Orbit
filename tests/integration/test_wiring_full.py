"""Integration test: wiring.py all lazy getters with successful imports.
Each getter follows the same try/except pattern. Mocking imports to SUCCEED
exercises ~200 statements across 35 methods in one test.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from orbit.integration.wiring import OrbitWiring, configure_wiring, get_wiring


# Mock ALL classes that wiring.py lazily imports
_MODULES_TO_MOCK = [
    "orbit.observability.trajectory",
    "orbit.memory.episodic",
    "orbit.memory.profile",
    "orbit.memory.agentic",
    "orbit.evolution.distill",
    "orbit.evolution.anchor",
    "orbit.evolution.grpo",
    "orbit.evolution.inject",
    "orbit.evolution.llm_distill",
    "orbit.metacognition.monitor",
    "orbit.agents.mcts",
    "orbit.router.bandit",
    "orbit.observability.drift_detector",
    "orbit.metacognition.pid_controller",
    "orbit.testing.conformal",
    "orbit.graph.spectral",
    "orbit.compression.ib_compressor",
    "orbit.context.ot_matcher",
    "orbit.agents.mdp",
    "orbit.hallucination.abstract_interp",
    "orbit.compose.mechanism",
    "orbit.evolution.pac_bounds",
    "orbit.graph.engines.slicer",
    "orbit.hallucination.l9_temporal",
    "orbit.hallucination.l10_separation",
    "orbit.agents.bisim",
    "orbit.goal.bft",
    "orbit.observability.attribution",
    "orbit.review.mdl_scorer",
    "orbit.observability.dp",
    "orbit.graph.tda",
    "orbit.metacognition.free_energy",
    "orbit.evolution.info_geom",
    "orbit.hallucination.effect_tracker",
    "orbit.gateway.client",
]


@pytest.fixture(autouse=True)
def _mock_imports():
    """Make all lazy imports succeed by inserting mock modules."""
    saved = {}
    for mod_name in _MODULES_TO_MOCK:
        mock_mod = MagicMock()
        # Each module has a class with the same name as the last component
        class_name = mod_name.split(".")[-1]
        # Create a class-like mock
        mock_cls = MagicMock()
        setattr(mock_mod, _camel_case(class_name), mock_cls)
        saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_mod
    yield
    for mod_name, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = orig


def _camel_case(snake: str) -> str:
    """snake_case → CamelCase"""
    return "".join(w.capitalize() for w in snake.split("_"))


class TestWiringAllGetters:
    """Every _get_* method returns non-None when imports succeed."""

    @pytest.fixture
    def w(self):
        return OrbitWiring(db_path=":memory:")

    # Core getters
    def test_get_trajectory(self, w): assert w._get_trajectory() is not None
    def test_get_episodic(self, w): assert w._get_episodic() is not None
    def test_get_profile(self, w): assert w._get_profile() is not None
    def test_get_agentic(self, w): assert w._get_agentic() is not None
    def test_get_distill(self, w): assert w._get_distill() is not None
    def test_get_anchor(self, w): assert w._get_anchor() is not None
    def test_get_grpo(self, w): assert w._get_grpo() is not None
    def test_get_injector(self, w): assert w._get_injector() is not None
    def test_get_llm_distill(self, w): assert w._get_llm_distill() is not None
    def test_get_monitor(self, w): assert w._get_monitor() is not None
    def test_get_mcts(self, w): assert w._get_mcts() is not None
    def test_get_bandit(self, w): assert w._get_bandit() is not None
    def test_get_drift(self, w): assert w._get_drift() is not None
    def test_get_pid(self, w): assert w._get_pid() is not None
    def test_get_conformal(self, w): assert w._get_conformal() is not None
    def test_get_spectral(self, w): assert w._get_spectral() is not None
    def test_get_ib(self, w): assert w._get_ib() is not None
    def test_get_ot(self, w): assert w._get_ot() is not None
    def test_get_mdp(self, w): assert w._get_mdp() is not None
    def test_get_abs_pipe(self, w): assert w._get_abs_pipe() is not None
    def test_get_vcg(self, w): assert w._get_vcg() is not None
    def test_get_pac(self, w): assert w._get_pac() is not None
    def test_get_slicer(self, w): assert w._get_slicer() is not None
    def test_get_temporal(self, w): assert w._get_temporal() is not None
    def test_get_sep(self, w): assert w._get_sep() is not None
    def test_get_bisim(self, w): assert w._get_bisim() is not None
    def test_get_bft(self, w): assert w._get_bft() is not None
    def test_get_shapley(self, w): assert w._get_shapley() is not None
    def test_get_mdl(self, w): assert w._get_mdl() is not None
    def test_get_dp(self, w): assert w._get_dp() is not None
    def test_get_tda(self, w): assert w._get_tda() is not None
    def test_get_fe(self, w): assert w._get_fe() is not None
    def test_get_ig(self, w): assert w._get_ig() is not None
    def test_get_effect(self, w): assert w._get_effect() is not None
    def test_get_llm_client(self, w): assert w._get_llm_client() is not None

    # Cached: second call returns same instance
    def test_caching(self, w):
        a = w._get_trajectory()
        b = w._get_trajectory()
        assert a is b


class TestWiringLifecycleWithMocks:
    """on_task_start/end with successful imports."""

    @pytest.fixture
    def w(self):
        return OrbitWiring(db_path=":memory:")

    def test_on_task_start_end_full(self, w):
        w.on_task_start("t1", "test goal", "proj-1")
        w.set_model_tier("T2")
        w.record_event("t1", "event1", "success", ["tag1"])
        result = w.enhance_prompt("base", category="test", keywords=["test"])
        assert isinstance(result, str)
        w.on_task_end("t1", "completed", 0.95, turns=3, tool_calls=5)

    def test_configure_and_get_wiring(self, tmp_path):
        db = str(tmp_path / "w.db")
        w = configure_wiring(db)
        assert w._db_path == db
        w2 = get_wiring()
        assert w is w2


class TestEnhancePromptWithInjector:
    """enhance_prompt with working injector + agentic."""

    def test_with_type_sig(self):
        w = OrbitWiring(db_path=":memory:")
        with patch("orbit.hallucination.l4_type.TypeDirectedSynthesizer.constrain", return_value=["c1"]):
            result = w.enhance_prompt("base", type_sig="int -> str")
            assert isinstance(result, str)

    def test_with_injector_working(self):
        w = OrbitWiring(db_path=":memory:")
        mock_inj = MagicMock()
        mock_inj.inject.return_value = "enhanced"
        w._injector = mock_inj
        result = w.enhance_prompt("base", category="security", keywords=["sql"])
        assert "enhanced" in result

    def test_with_agentic_suggestions(self):
        w = OrbitWiring(db_path=":memory:")
        mock_am = MagicMock()
        mock_s = MagicMock()
        mock_s.action = "validate inputs"
        mock_s.utility = 0.88
        mock_am.suggest.return_value = [mock_s]
        w._agentic = mock_am
        result = w.enhance_prompt("base", keywords=["xss"])
        assert isinstance(result, str)
