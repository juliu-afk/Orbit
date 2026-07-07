"""testing/strategies/evolutionary_selector.py 单元测试——进化式策略选择器。"""

from __future__ import annotations

import pytest

from orbit.testing.strategies.evolutionary_selector import (
    EvolutionaryRouter,
    StrategyRecord,
)


class TestStrategyRecord:
    """StrategyRecord 统计计算。"""

    def test_win_rate_zero_when_no_games(self):
        """无记录 → win_rate = 0。"""
        record = StrategyRecord(strategy_name="intention_driven", module_pattern="scheduler.*")
        assert record.win_rate == 0.0

    def test_win_rate_calculation(self):
        """赢 3/5 → 0.6。"""
        record = StrategyRecord(
            strategy_name="path_sensitive",
            module_pattern="scheduler.*",
            win_count=3,
            total_count=5,
        )
        assert record.win_rate == 0.6

    def test_confidence_low_with_few_samples(self):
        """样本不足 → 低置信度。"""
        record = StrategyRecord(strategy_name="a", module_pattern="*", total_count=2)
        assert record.confidence == 0.2

    def test_confidence_max_at_10_samples(self):
        """10+ 样本 → 满置信度。"""
        record = StrategyRecord(strategy_name="a", module_pattern="*", total_count=10)
        assert record.confidence == 1.0


class TestEvolutionaryRouter:
    """EvolutionaryRouter——路由决策。"""

    @pytest.mark.asyncio
    async def test_route_returns_none_with_no_history(self):
        """无历史数据 → None（回退 AB）。"""
        router = EvolutionaryRouter(knowledge=None)
        _ = router._cache  # 触发缓存初始化
        best = await router.route("scheduler.state_machine", ["intention_driven", "path_sensitive"])
        assert best is None

    @pytest.mark.asyncio
    async def test_route_returns_none_with_insufficient_samples(self):
        """历史 < MIN_SAMPLES_FOR_ROUTING → None。"""
        router = EvolutionaryRouter(knowledge=None)
        router._cache["scheduler.state_machine"] = [
            StrategyRecord(strategy_name="intention_driven", module_pattern="scheduler.*", win_count=2, total_count=2),
        ]
        best = await router.route("scheduler.state_machine", ["intention_driven", "path_sensitive"])
        assert best is None  # 2 < 3 MIN_SAMPLES

    @pytest.mark.asyncio
    async def test_route_selects_best_with_enough_history(self):
        """足够历史 + 显著差距 → 自动路由。"""
        router = EvolutionaryRouter(knowledge=None)
        router._cache["scheduler.state_machine"] = [
            StrategyRecord(strategy_name="intention_driven", module_pattern="scheduler.*", win_count=8, total_count=10),
            StrategyRecord(strategy_name="path_sensitive", module_pattern="scheduler.*", win_count=3, total_count=10),
        ]
        best = await router.route("scheduler.state_machine", ["intention_driven", "path_sensitive"])
        assert best == "intention_driven"  # 差距 0.5 > 0.20

    @pytest.mark.asyncio
    async def test_route_returns_none_when_delta_too_small(self):
        """胜率差距不够大 → None（回退 AB）。"""
        router = EvolutionaryRouter(knowledge=None)
        router._cache["scheduler.state_machine"] = [
            StrategyRecord(strategy_name="intention_driven", module_pattern="scheduler.*", win_count=6, total_count=10),
            StrategyRecord(strategy_name="path_sensitive", module_pattern="scheduler.*", win_count=5, total_count=10),
        ]
        best = await router.route("scheduler.state_machine", ["intention_driven", "path_sensitive"])
        assert best is None  # 差距 0.1 < 0.20

    @pytest.mark.asyncio
    async def test_route_filters_unavailable_strategies(self):
        """只考虑 available_strategies 中的策略。"""
        router = EvolutionaryRouter(knowledge=None)
        router._cache["scheduler.state_machine"] = [
            StrategyRecord(strategy_name="intention_driven", module_pattern="scheduler.*", win_count=10, total_count=10),
            StrategyRecord(strategy_name="path_sensitive", module_pattern="scheduler.*", win_count=8, total_count=10),
        ]
        best = await router.route("scheduler.state_machine", ["intention_driven"])
        assert best == "intention_driven"

    def test_cache_update_new_record(self):
        """首次记录 → 新建缓存条目。"""
        router = EvolutionaryRouter(knowledge=None)
        router._update_cache("new.module", "intention_driven", won=True, score=0.85, ts="now")
        assert "new.module" in router._cache
        assert router._cache["new.module"][0].win_rate == 1.0
        assert router._cache["new.module"][0].total_count == 1

    def test_cache_update_existing_record(self):
        """已有记录 → 累加。"""
        router = EvolutionaryRouter(knowledge=None)
        router._update_cache("mod", "strat_a", won=True, score=0.80, ts="t1")
        router._update_cache("mod", "strat_a", won=False, score=0.60, ts="t2")
        record = router._cache["mod"][0]
        assert record.total_count == 2
        assert record.win_count == 1
        assert record.win_rate == 0.5
