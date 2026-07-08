"""Shapley值贡献归因 (V14.2+Theory 方向6). P2-1: 蒙特卡洛近似 + 精确."""
from __future__ import annotations
import math
import random
from itertools import combinations

class ShapleyAttribution:
    @staticmethod
    def attribute(agents: list[str], value_fn, method: str = "exact") -> dict[str, float]:
        """n≤12→精确, n>12→蒙特卡洛采样."""
        n = len(agents)
        if n == 0: return {}
        if method == "mc" or n > 12:
            return ShapleyAttribution._mc_sample(agents, value_fn)
        return ShapleyAttribution._exact(agents, value_fn)

    @staticmethod
    def _exact(agents: list[str], value_fn) -> dict[str, float]:
        n = len(agents)
        vals = {a: 0.0 for a in agents}
        for i, agent in enumerate(agents):
            for k in range(n):
                for subset in combinations(set(agents) - {agent}, k):
                    s = len(subset)
                    weight = (math.factorial(s) * math.factorial(n - s - 1)
                              / math.factorial(n))
                    vals[agent] += weight * (value_fn(set(subset) | {agent})
                                             - value_fn(set(subset)))
        return vals

    @staticmethod
    def _mc_sample(agents: list[str], value_fn, samples: int = 2000) -> dict[str, float]:
        """蒙特卡洛近似——Castro et al. 2009."""
        n = len(agents)
        vals = {a: 0.0 for a in agents}
        for _ in range(samples):
            perm = list(agents)
            random.shuffle(perm)
            subset = set()
            prev_v = value_fn(set())
            for agent in perm:
                new_v = value_fn(subset | {agent})
                vals[agent] += new_v - prev_v
                subset.add(agent)
                prev_v = new_v
        return {a: v / samples for a, v in vals.items()}

    @staticmethod
    def rank(agents: list[str], value_fn) -> list[tuple[str, float]]:
        return sorted(ShapleyAttribution.attribute(agents, value_fn).items(),
                      key=lambda x: -x[1])
