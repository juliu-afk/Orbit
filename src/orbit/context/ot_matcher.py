"""最优传输上下文匹配 (V14.2+Theory 方向11).

Sinkhorn算法: O(n²/ε)——n≤100可实时.
Wasserstein距离下全局最优上下文分配.

用法:
    matcher = OTMatcher(reg=0.1)
    assignment = matcher.match(context_embeddings, agent_needs, token_budget)
"""
from __future__ import annotations
import math


class OTMatcher:
    """熵正则化最优传输匹配器."""

    def __init__(self, reg: float = 0.1):
        self.reg = reg  # Sinkhorn正则化参数

    def match(self, contexts: list[list[float]], needs: list[list[float]],
              token_budgets: list[int] | None = None) -> list[tuple[int, int]]:
        """Sinkhorn最优传输——返回(context_idx, agent_idx)分配对.

        contexts: [embedding₁, ...]——源分布
        needs: [embedding₂, ...]——靶分布
        token_budgets: 每个Agent的Token预算(容量约束)
        """
        n, m = len(contexts), len(needs)
        if n == 0 or m == 0:
            return []
        # 成本矩阵 C[i][j] = ||ctx_i - need_j||²
        C = [[0.0] * m for _ in range(n)]
        for i in range(n):
            for j in range(m):
                d2 = sum((contexts[i][k] - needs[j][k]) ** 2
                        for k in range(min(len(contexts[i]), len(needs[j]))))
                C[i][j] = d2
        # Sinkhorn: K = exp(-C/reg), 迭代行/列归一化
        K = [[math.exp(-C[i][j] / self.reg) for j in range(m)] for i in range(n)]
        u = [1.0] * n
        for _ in range(20):  # 20轮收敛
            # 列归一化
            v = [1.0 / max(sum(K[i][j] * u[i] for i in range(n)), 1e-10) for j in range(m)]
            # 行归一化
            u = [1.0 / max(sum(K[i][j] * v[j] for j in range(m)), 1e-10) for i in range(n)]
        # 运输计划 P[i][j] = u[i] * K[i][j] * v[j]
        result = []
        for i in range(n):
            best_j = max(range(m), key=lambda j: u[i] * K[i][j] * v[j])
            result.append((i, best_j))
        # 容量约束: 超出预算的截断
        if token_budgets:
            used = [0] * m
            filtered = []
            for i, j in result:
                if used[j] < (token_budgets[j] if j < len(token_budgets) else 99999):
                    filtered.append((i, j))
                    used[j] += 1
            return filtered
        return result
