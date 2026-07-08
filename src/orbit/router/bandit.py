"""Thompson Sampling 多臂 Bandit 路由器 (V14.2+Theory 方向 2).

Beta-Bernoulli 共轭——每模型臂维护 Beta(α, β) 后验。
收敛后遗憾上界 O(√(kT ln T))，无需环境变量之外的配置。

用法:
    bandit = ThompsonBandit(["tier_0", "tier_1", "tier_2", "tier_3"])
    tier = bandit.select()             # 采样各臂→选最大
    bandit.update(tier, success=True, latency_ms=1200)
"""

from __future__ import annotations

import math
import os
import random


class ThompsonBandit:
    """Thompson Sampling 模型层级路由器。

    每个 tier 维护 Beta(α, β):
      α = 1 + 成功次数（先验 Beta(1,1) = Uniform(0,1)）
      β = 1 + 失败次数
    延迟 > 3s → 额外 β+0.5（软惩罚慢模型）
    """

    def __init__(
        self,
        arms: list[str] | None = None,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
    ) -> None:
        arms = arms or ["tier_0", "tier_1", "tier_2", "tier_3"]
        self._posteriors: dict[str, dict[str, float]] = {
            arm: {"alpha": prior_alpha, "beta": prior_beta} for arm in arms
        }

    def select(self) -> str:
        """Thompson 采样——从各臂 Beta 后验采样，返回最大采样值对应的臂。

        低方差臂（数据多）采样值稳定，高方差臂（数据少）有机会被探索。
        """
        best_arm = self._posteriors.keys().__iter__().__next__()
        best_sample = -1.0
        for arm, p in self._posteriors.items():
            sample = random.betavariate(p["alpha"], p["beta"])
            if sample > best_sample:
                best_sample = sample
                best_arm = arm
        return best_arm

    def update(self, arm: str, success: bool, latency_ms: float = 0.0) -> None:
        """观察奖励，更新后验。

        success=True  → α+1（成功强化）
        success=False → β+1（失败弱化）
        latency > 3000ms → β+0.5（软惩罚——太慢的模型降权但不等于失败）
        """
        if arm not in self._posteriors:
            return
        p = self._posteriors[arm]
        if success:
            p["alpha"] += 1.0
        else:
            p["beta"] += 1.0
        # 延迟软惩罚——避免因等待时间而丢弃好模型
        if latency_ms > 3000:
            p["beta"] += 0.5

    @property
    def posteriors(self) -> dict[str, dict[str, float]]:
        """只读后验（供驾驶舱展示）。"""
        return {k: dict(v) for k, v in self._posteriors.items()}

    def reset_arm(self, arm: str) -> None:
        """重置某臂后验为先验——变点检测触发时调用。"""
        if arm in self._posteriors:
            self._posteriors[arm] = {"alpha": 1.0, "beta": 1.0}


def is_bandit_enabled() -> bool:
    """检查 ORBIT_ROUTER_BANDIT 环境变量。"""
    return os.environ.get("ORBIT_ROUTER_BANDIT", "").strip() == "1"
