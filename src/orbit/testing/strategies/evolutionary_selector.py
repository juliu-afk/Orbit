"""进化式策略选择器 —— AB 历史积累 → 自动路由最优策略。

L1 (P3): AB 对比结果沉淀到 knowledge/ → 同类模块自动路由到历史胜率最高的策略。
胜率差距 >20% 时直接跳过 AB，节省计算资源。

对标: Orbit 研究报告 §8.4 L1 + Google MuRS ML suppression（反馈驱动自适应）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.testing.evolutionary_selector")


@dataclass
class StrategyRecord:
    """一条策略历史记录。"""

    strategy_name: str
    module_pattern: str  # 模块名模式（如 "scheduler.*"）
    win_count: int = 0
    total_count: int = 0
    avg_mutation_score: float = 0.0
    last_used: str = ""  # ISO timestamp

    @property
    def win_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.win_count / self.total_count

    @property
    def confidence(self) -> float:
        """置信度——基于样本量。>10 次 → 高置信。"""
        return min(1.0, self.total_count / 10.0)


@dataclass
class EvolutionaryRouter:
    """进化式策略路由器。

    Usage:
        router = EvolutionaryRouter(knowledge_store)
        best = await router.route(module_name, available_strategies)
        if best:
            # 直接用历史胜者——跳过 AB
        else:
            # 历史不足——回退 AB 对比
    """

    # AB 历史不足时至少需要多少次才可自动路由
    MIN_SAMPLES_FOR_ROUTING: int = 3
    # 胜率差距阈值——超过此值直接跳过 AB
    WIN_RATE_DELTA_THRESHOLD: float = 0.20

    def __init__(self, knowledge=None):
        self._knowledge = knowledge
        # 内存缓存——减少 knowledge/ 查询
        self._cache: dict[str, list[StrategyRecord]] = {}

    async def route(
        self,
        module_name: str,
        available_strategies: list[str],
    ) -> str | None:
        """为给定模块选择最优策略。

        Args:
            module_name: 模块名（如 "scheduler.state_machine"）
            available_strategies: 可用策略列表（如 ["intention_driven", "path_sensitive"]）

        Returns:
            最优策略名——若历史不足或胜率差距不够大，返回 None（调用方应回退 AB）
        """
        # 1. 从 knowledge/ 加载历史（带缓存）
        records = await self._load_history(module_name)

        # 2. 过滤出历史胜率足够高的策略
        candidates = [
            r for r in records
            if r.strategy_name in available_strategies
            and r.total_count >= self.MIN_SAMPLES_FOR_ROUTING
            and r.confidence >= 0.5  # 至少中等置信度
        ]

        if not candidates:
            logger.info(
                "evolutionary_route_insufficient_data",
                module=module_name,
                records=len(records),
                min_samples=self.MIN_SAMPLES_FOR_ROUTING,
            )
            return None  # 历史不足——回退 AB

        # 3. 按 win_rate 排序
        candidates.sort(key=lambda r: r.win_rate, reverse=True)
        best = candidates[0]

        # 4. 检查是否显著优于第二名
        if len(candidates) >= 2:
            second_best = candidates[1]
            delta = best.win_rate - second_best.win_rate
            if delta < self.WIN_RATE_DELTA_THRESHOLD:
                logger.info(
                    "evolutionary_route_too_close",
                    module=module_name,
                    best=best.strategy_name,
                    best_rate=f"{best.win_rate:.0%}",
                    second=second_best.strategy_name,
                    second_rate=f"{second_best.win_rate:.0%}",
                    delta=f"{delta:.1%}",
                )
                return None  # 差距不够大——回退 AB

        logger.info(
            "evolutionary_route_selected",
            module=module_name,
            strategy=best.strategy_name,
            win_rate=f"{best.win_rate:.0%}",
            samples=best.total_count,
            confidence=f"{best.confidence:.0%}",
        )
        return best.strategy_name

    async def record_ab_result(
        self,
        module_name: str,
        strategy_a: str,
        score_a: float,
        strategy_b: str,
        score_b: float,
    ) -> None:
        """记录一次 AB 对比结果——累积到 knowledge/。

        当 AB 结果持续积累，同类模块的历史数据自动驱动路由决策。
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        # 判定胜者
        winner = strategy_a if score_a > score_b else strategy_b
        loser = strategy_b if winner == strategy_a else strategy_a
        winner_score = max(score_a, score_b)
        loser_score = min(score_a, score_b)

        # 更新 winner 记录
        self._update_cache(module_name, winner, won=True, score=winner_score, ts=now)
        # 更新 loser 记录
        self._update_cache(module_name, loser, won=False, score=loser_score, ts=now)

        # 持久化到 knowledge/
        if self._knowledge:
            try:
                await self._knowledge.upsert_ab_result(
                    module=module_name,
                    strategy=winner,
                    won=True,
                    score=winner_score,
                    timestamp=now,
                )
                await self._knowledge.upsert_ab_result(
                    module=module_name,
                    strategy=loser,
                    won=False,
                    score=loser_score,
                    timestamp=now,
                )
            except Exception as e:
                logger.warning("evolutionary_record_persist_failed", error=str(e))

    def _update_cache(
        self, module_name: str, strategy: str, *, won: bool, score: float, ts: str,
    ) -> None:
        """更新内存缓存。"""
        if module_name not in self._cache:
            self._cache[module_name] = []

        for record in self._cache[module_name]:
            if record.strategy_name == strategy:
                record.total_count += 1
                if won:
                    record.win_count += 1
                # 移动平均更新 mutation_score
                alpha = 1.0 / record.total_count
                record.avg_mutation_score = (
                    (1 - alpha) * record.avg_mutation_score + alpha * score
                )
                record.last_used = ts
                return

        # 新记录
        self._cache[module_name].append(StrategyRecord(
            strategy_name=strategy,
            module_pattern=module_name.split(".")[0] + ".*" if "." in module_name else module_name,
            win_count=1 if won else 0,
            total_count=1,
            avg_mutation_score=score,
            last_used=ts,
        ))

    async def _load_history(self, module_name: str) -> list[StrategyRecord]:
        """从 knowledge/ 加载模块的策略历史。"""
        if module_name in self._cache:
            return self._cache[module_name]

        records: list[StrategyRecord] = []
        if self._knowledge:
            try:
                raw = await self._knowledge.get_ab_results(module=module_name)
                for item in (raw or []):
                    records.append(StrategyRecord(
                        strategy_name=item.get("strategy", ""),
                        module_pattern=item.get("module", module_name),
                        win_count=item.get("win_count", 0),
                        total_count=item.get("total_count", 1),
                        avg_mutation_score=item.get("avg_score", 0.0),
                        last_used=item.get("last_used", ""),
                    ))
            except Exception as e:
                logger.debug("evolutionary_history_load_failed", error=str(e))

        self._cache[module_name] = records
        return records
