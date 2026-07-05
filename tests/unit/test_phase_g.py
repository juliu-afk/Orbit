"""Phase G 单元测试——GEPA/SCOPE."""
from __future__ import annotations

from orbit.evolution.scope import ScopeMemory


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
