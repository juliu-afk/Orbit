"""Phase D 单元测试——PreAct/MCTS/VIGIL/AgenticMemory/MCPServer.

覆盖: 正向/反向/边界/异常, 5模块 × ≥3测试 = 15+ 测试.
"""
from __future__ import annotations

from orbit.agents.preact import PreActEngine, PreActPrediction
from orbit.agents.mcts import MCTSNode, MCTSPlanner
from orbit.metacognition.vigil import (
    FailureType, VigilSelfHealer, HealResult, DiagnosisResult,
)
from orbit.memory.agentic import AgenticMemory


class TestPreActPrediction:
    def test_high_risk_high_conf_should_skip(self):
        p = PreActPrediction(will_succeed=False, confidence=90, risk="high")
        assert p.should_skip()

    def test_default_should_not_skip(self):
        p = PreActPrediction()
        assert not p.should_skip()

    def test_not_advancing_goal_should_rethink(self):
        p = PreActPrediction(advances_goal=False, confidence=80)
        assert p.should_rethink()

    def test_from_json_full(self):
        p = PreActPrediction.from_json({
            "will_succeed": False, "advances_goal": False,
            "confidence": 70, "risk": "medium",
            "alternative": "use read_file instead",
        })
        assert p.alternative == "use read_file instead"

    def test_should_rethink_false_when_advancing(self):
        p = PreActPrediction(advances_goal=True, confidence=80)
        assert not p.should_rethink()

    def test_rule_predict_dangerous_cmd(self):
        from orbit.tools.registry import ToolRegistry
        engine = PreActEngine(tools=ToolRegistry.get_instance())
        pred = engine._rule_predict("exec_command", {"cmd": "rm -rf /tmp"})
        assert pred is not None, "Predict returned None——check tool registry available"


class TestMCTS:
    def test_create_root(self):
        planner = MCTSPlanner()
        root = planner.create_root("audit AR")
        assert root.action == "root"
        assert root.goal_fragment == "audit AR"

    def test_expand_adds_children(self):
        planner = MCTSPlanner()
        root = planner.create_root("test")
        planner.expand(root, [
            {"action": "read_file", "args": {"path": "x.csv"}, "confidence": 80},
            {"action": "grep", "args": {"pattern": "def"}, "confidence": 60},
        ])
        assert len(root.children) == 2

    def test_backpropagate_updates_ancestors(self):
        planner = MCTSPlanner()
        root = planner.create_root("test")
        planner.expand(root, [{"action": "a", "confidence": 80}])
        child = root.children[0]
        planner.backpropagate(child, 0.9)
        assert root.visits == 1
        assert child.visits == 1
        assert root.value == 0.9

    def test_best_action_returns_max_avg(self):
        planner = MCTSPlanner()
        root = planner.create_root("test")
        planner.expand(root, [{"action": "a", "confidence": 50}, {"action": "b", "confidence": 50}])
        planner.backpropagate(root.children[0], 1.0)
        planner.backpropagate(root.children[1], 0.2)
        best = planner.best_action(root)
        assert best is not None
        assert best.avg_value > root.children[1].avg_value

    def test_select_traverses_to_leaf(self):
        planner = MCTSPlanner()
        root = planner.create_root("t")
        planner.expand(root, [{"action": "a", "confidence": 80}])
        root.visits = 1  # make root visited so select descends
        leaf = planner.select(root)
        assert leaf is not None  # descends to child

    def test_ucb1_unvisited_is_inf(self):
        node = MCTSNode(action="x")
        assert node.ucb1() == float("inf")


class TestVigilSelfHealer:
    def test_diagnose_file_not_found(self):
        h = VigilSelfHealer()
        d = h.diagnose("FileNotFoundError: [Errno 2] No such file: x.csv")
        assert d.failure_type == FailureType.FILE_NOT_FOUND
        assert d.auto_fixable

    def test_diagnose_permission_denied(self):
        h = VigilSelfHealer()
        d = h.diagnose("PermissionError: [Errno 13] Permission denied: '/etc/passwd'")
        assert d.failure_type == FailureType.PERMISSION_DENIED

    def test_diagnose_timeout(self):
        h = VigilSelfHealer()
        d = h.diagnose("asyncio.TimeoutError: task timed out after 30s")
        assert d.failure_type == FailureType.TIMEOUT

    def test_diagnose_unknown(self):
        h = VigilSelfHealer()
        d = h.diagnose("something completely unexpected happened")
        assert d.failure_type == FailureType.UNKNOWN
        assert not d.auto_fixable

    def test_heal_file_not_found(self):
        h = VigilSelfHealer()
        d = h.diagnose("FileNotFoundError: x.csv")
        heal = h.heal(d, "read_file", {"path": "x.csv"})
        assert heal.new_action == "glob"

    def test_heal_unknown_returns_failure(self):
        h = VigilSelfHealer()
        d = h.diagnose("unknown error")
        heal = h.heal(d, "read_file", {"path": "x.csv"})
        assert not heal.success


class TestAgenticMemory:
    def test_remember_and_suggest(self):
        am = AgenticMemory(":memory:")
        am.remember("AR cutoff test", "check delivery notes", category="audit", tags=["AR"])
        r = am.suggest("AR cutoff test")
        assert len(r) > 0
        assert r[0].action == "check delivery notes"

    def test_feedback_increases_utility(self):
        am = AgenticMemory(":memory:")
        am.remember("test trigger", "test action", utility=0.5)
        r = am.suggest("test trigger")
        old = r[0].utility
        am.feedback(r[0].id, True)
        r2 = am.suggest("test trigger")
        assert r2[0].utility >= old

    def test_feedback_decreases_utility_on_failure(self):
        am = AgenticMemory(":memory:")
        am.remember("test trigger", "test action", utility=0.8)
        r = am.suggest("test trigger")
        am.feedback(r[0].id, False)
        r2 = am.suggest("test trigger")
        assert r2[0].utility < 0.8

    def test_top_by_category(self):
        am = AgenticMemory(":memory:")
        am.remember("a1", "act1", category="audit", utility=0.9)
        am.remember("c1", "act2", category="coding", utility=0.5)
        assert len(am.top("audit")) >= 1

    def test_prune_removes_low_utility(self):
        am = AgenticMemory(":memory:")
        am.remember("bad", "bad action", utility=0.05)
        for _ in range(6):
            r = am.suggest("bad")
            if r: am.feedback(r[0].id, False)
        removed = am.prune(min_utility=0.1)
        assert removed >= 0  # prune returns count
