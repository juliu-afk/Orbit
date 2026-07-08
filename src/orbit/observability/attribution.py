"""Shapley值贡献归因 (V14.2+Theory 方向6).

φᵢ = Σ (|S|!(n-|S|-1)!/n!)·[v(S∪{i})-v(S)]
边际贡献的加权平均——满足效率/对称/空玩家/可加性公理.

用法:
    attr = ShapleyAttribution()
    values = attr.attribute(agents, value_function)
"""
from __future__ import annotations
import math
from itertools import combinations


class ShapleyAttribution:
    """Shapley值——多Agent贡献的形式化公平分配."""

    @staticmethod
    def attribute(agents: list[str],
                  value_fn) -> dict[str, float]:
        """计算每个Agent的Shapley值.

        value_fn(S: set[str]) -> float: Agent子集S协作的期望价值
        """
        n = len(agents)
        if n == 0:
            return {}
        values: dict[str, float] = {a: 0.0 for a in agents}
        for i, agent in enumerate(agents):
            for k in range(n):
                for subset in combinations(set(agents) - {agent}, k):
                    s = len(subset)
                    weight = (math.factorial(s) * math.factorial(n - s - 1)
                              / math.factorial(n))
                    v_without = value_fn(set(subset))
                    v_with = value_fn(set(subset) | {agent})
                    values[agent] += weight * (v_with - v_without)
        return values

    @staticmethod
    def rank(agents: list[str], value_fn) -> list[tuple[str, float]]:
        """排序——高Shapley值Agent贡献大."""
        vals = ShapleyAttribution.attribute(agents, value_fn)
        return sorted(vals.items(), key=lambda x: -x[1])
