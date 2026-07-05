"""Phase G 单元测试——GEPA/SCOPE."""
from __future__ import annotations

from orbit.evolution.distill import DistillationEngine, StrategyPrinciple
from orbit.evolution.gepa import GEPAPopulation
from orbit.evolution.scope import ScopeMemory


class TestGEPAPopulation:
    def test_select_elite(self):
        pop = GEPAPopulation(population_size=10, elite_size=3)
        principles = [
            StrategyPrinciple(id="1", principle="a", utility_score=0.3),
            StrategyPrinciple(id="2", principle="b", utility_score=0.9),
            StrategyPrinciple(id="3", principle="c", utility_score=0.7),
            StrategyPrinciple(id="4", principle="d", utility_score=0.5),
        ]
        elite = pop.select_elite(principles)
        assert len(elite) == 3
        assert elite[0].utility_score == 0.9

    def test_select_parents_different(self):
        pop = GEPAPopulation()
        principles = [
            StrategyPrinciple(id=str(i), principle=f"p{i}", utility_score=0.3 + i * 0.1)
            for i in range(6)
        ]
        p1, p2 = pop.select_parents(principles)
        assert p1.id != p2.id or len(principles) == 1



class TestScopeMemory:
    def test_add_tactical(self):
        scope = ScopeMemory(":memory:")
        scope.add_tactical("t1", "API rate limit 10/min")
        rules = scope.get_tactical_for_task("t1")
        assert len(rules) == 1

    def test_tactical_upgrade_to_strategic(self):
        scope = ScopeMemory(":memory:")
        for tid in ["t1", "t2", "t3"]:
            scope.add_tactical(tid, "API rate limit 10/min")
        strategic = scope.get_strategic("API rate limit")
        assert len(strategic) > 0

    def test_add_strategic_direct(self):
        scope = ScopeMemory(":memory:")
        r = scope.add_strategic("Always validate JSON before parsing", 0.8)
        assert r is not None
        all_rules = scope.get_strategic_all()
        assert len(all_rules) >= 1

    def test_add_strategic_dedup(self):
        scope = ScopeMemory(":memory:")
        scope.add_strategic("Always validate JSON before parsing input", 0.8)
        scope.add_strategic("Always validate JSON before parsing the input data", 0.9)
        all_rules = scope.get_strategic_all()
        # 高度相似 → 去重
        assert len(all_rules) == 1

    def test_feedback(self):
        scope = ScopeMemory(":memory:")
        r = scope.add_strategic("test rule", 0.5)
        scope.feedback(r.id, True)
        updated = scope.get_strategic_all()[0]
        assert updated.utility > 0.5

    def test_cleanup_tactical(self):
        scope = ScopeMemory(":memory:")
        scope.add_tactical("t1", "temp rule")
        scope.cleanup_tactical("t1")
        assert len(scope.get_tactical_for_task("t1")) == 0
