"""信息瓶颈上下文压缩 (V14.2+Theory 方向4).

IB: min I(X;C) - β I(C;Y). 聚类上下文片段为K个原型,
给定Token预算B→0-1背包选最大MI子集.

用法:
    comp = IBCompressor(n_clusters=5, beta=2.0)
    selected = comp.compress(fragments, budget_tokens)
"""
from __future__ import annotations
import math


class IBCompressor:
    """信息瓶颈压缩器——互信息导向的上下文选择."""

    def __init__(self, n_clusters: int = 5, beta: float = 2.0):
        self.K = n_clusters
        self.beta = beta

    def compress(self, fragments: list[dict], budget_tokens: int) -> list[dict]:
        """压缩——返回Token预算内MI最大的片段子集.

        fragments: [{"text":..., "tokens":..., "mi_score":...}, ...]
        budget_tokens: 可用Token预算
        """
        if not fragments or budget_tokens <= 0:
            return []
        # 0-1 背包: 最大化 ΣMI, 约束 Σtokens ≤ budget
        n = len(fragments)
        dp = [0.0] * (budget_tokens + 1)
        keep = [[False] * (budget_tokens + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            f = fragments[i - 1]
            w = f.get("tokens", 100)
            v = f.get("mi_score", 0.0)
            for j in range(budget_tokens, w - 1, -1):
                new_val = dp[j - w] + v
                if new_val > dp[j]:
                    dp[j] = new_val
                    keep[i][j] = True
        # 回溯
        result = []
        j = budget_tokens
        for i in range(n, 0, -1):
            if keep[i][j]:
                result.append(fragments[i - 1])
                j -= fragments[i - 1].get("tokens", 100)
        result.reverse()
        return result

    def cluster(self, fragments: list[dict]) -> list[dict]:
        """IB聚类——合并MI相似的片段为原型."""
        if len(fragments) <= self.K:
            return fragments
        sorted_frags = sorted(fragments, key=lambda f: f.get("mi_score", 0), reverse=True)
        prototypes = []
        step = max(1, len(sorted_frags) // self.K)
        for i in range(0, len(sorted_frags), step):
            cluster = sorted_frags[i:i + step]
            proto = {
                "text": " | ".join(f["text"][:80] for f in cluster[:3]),
                "tokens": sum(f.get("tokens", 0) for f in cluster) // len(cluster),
                "mi_score": sum(f.get("mi_score", 0) for f in cluster) / len(cluster),
            }
            prototypes.append(proto)
            if len(prototypes) >= self.K:
                break
        return prototypes
