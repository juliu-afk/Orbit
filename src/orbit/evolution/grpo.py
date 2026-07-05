"""GRPO 策略评分器 (Phase E2).

WHY GRPO (Group Relative Policy Optimization):
  原始 GRPO 用强化学习训练 LLM 权重。我们不需要训练权重——
  我们只需要评估"这条策略原则是否让任务更成功"。
  模拟 GRPO 评分: 对比原则应用前后的成功率变化，动态调整效用分数。

设计:
  - 基线: 同类任务不使用原则时的平均成功率
  - 实验: 使用原则后的成功率
  - 效用 delta = (实验 - 基线) / max(基线, 0.01)
  - 自动剪枝: 低效用 + 高频应用 → 删除
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field

from orbit.evolution.distill import DistillationEngine, StrategyPrinciple

logger = structlog.get_logger("orbit.evolution.grpo")


@dataclass
class GRPOStats:
    """单个原则的 GRPO 统计。"""
    principle_id: str = ""
    baseline_success_rate: float = 0.5     # 基线成功率
    experimental_success_rate: float = 0.5  # 实验成功率
    total_trials: int = 0
    total_baseline_trials: int = 0
    utility_delta: float = 0.0
    last_updated: float = 0.0


class GRPOScorer:
    """GRPO 模拟评分器——基于任务结果调整原则效用。

    用法:
        scorer = GRPOScorer(engine=distill_engine)
        scorer.record_baseline(category="审计", success=True)  # 记录不使用原则的基线
        scorer.record_trial(principle_id, success=True)         # 记录使用原则后的结果
        scorer.update_utilities(category="审计")                # 批量更新效用
    """

    BASELINE_WINDOW = 20   # 基线滑动窗口大小
    TRIAL_WINDOW = 20      # 实验窗口大小

    def __init__(self, engine: DistillationEngine | None = None) -> None:
        self._engine = engine
        # 基线记录: category → [success_bools]
        self._baselines: dict[str, list[bool]] = {}
        # 实验记录: principle_id → [success_bools]
        self._trials: dict[str, list[bool]] = {}
        self._stats: dict[str, GRPOStats] = {}

    def record_baseline(self, category: str, success: bool) -> None:
        """记录一次不使用任何策略原则的任务结果。"""
        if category not in self._baselines:
            self._baselines[category] = []
        self._baselines[category].append(success)
        if len(self._baselines[category]) > self.BASELINE_WINDOW:
            self._baselines[category] = self._baselines[category][-self.BASELINE_WINDOW:]

    def record_trial(self, principle_id: str, success: bool) -> None:
        """记录一次使用特定策略原则的任务结果。"""
        if principle_id not in self._trials:
            self._trials[principle_id] = []
        self._trials[principle_id].append(success)
        if len(self._trials[principle_id]) > self.TRIAL_WINDOW:
            self._trials[principle_id] = self._trials[principle_id][-self.TRIAL_WINDOW:]

    def update_utilities(self, category: str = "") -> None:
        """基于基线 vs 实验对比，更新所有原则的效用分数。

        GRPO 模拟:
          - 实验成功率 > 基线 → 效用 +0.1 (好原则)
          - 实验成功率 ≈ 基线 → 效用不变 (中性)
          - 实验成功率 < 基线 → 效用 -0.05 (有害原则)
          - 低效用(<0.15) + 高频(≥10次) → 自动删除
        """
        if self._engine is None:
            return

        baseline_rate = self._baseline_rate(category)
        if baseline_rate == 0:
            baseline_rate = 0.5  # 默认基线

        principles = self._engine.top_principles(limit=200)
        removed = 0

        for p in principles:
            trials = self._trials.get(p.id, [])
            if len(trials) < 3:
                continue  # 样本不足，不更新

            exp_rate = sum(trials) / len(trials)
            delta = (exp_rate - baseline_rate) / max(baseline_rate, 0.01)

            # 更新原则效用
            if delta > 0.05:       # 显著优于基线
                self._engine.apply_feedback(p.id, True)
            elif delta < -0.05:    # 显著差于基线
                self._engine.apply_feedback(p.id, False)
                self._engine.apply_feedback(p.id, False)

            # 记录统计
            self._stats[p.id] = GRPOStats(
                principle_id=p.id,
                baseline_success_rate=baseline_rate,
                experimental_success_rate=exp_rate,
                total_trials=len(trials),
                total_baseline_trials=len(self._baselines.get(category, [])),
                utility_delta=delta,
            )

        # 自动剪枝
        if len(trials) >= 10:
            removed = self._engine.prune(min_score=0.15, min_applied=3)

        if removed:
            logger.info("grpo_pruned", removed=removed)
        logger.debug("grpo_update", category=category, baseline_rate=baseline_rate,
                     principles_updated=len(self._stats), pruned=removed)

    def get_stats(self, principle_id: str) -> GRPOStats | None:
        return self._stats.get(principle_id)

    def _baseline_rate(self, category: str) -> float:
        records = self._baselines.get(category, [])
        if not records:
            return 0.5
        return sum(records) / len(records)
