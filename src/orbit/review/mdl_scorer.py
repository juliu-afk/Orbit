"""最小描述长度评分 (V14.2+Theory 方向7).

MDL: L(D|H) + L(H) → min
L(H) = 程序压缩大小近似Kolmogorov复杂度
L(D|H) = 测试失败数

用法:
    scorer = MDLScorer()
    score = scorer.score(code, test_results)
"""
from __future__ import annotations
import gzip


class MDLScorer:
    """MDL简洁性评分——Occam剃刀的形式化."""

    @staticmethod
    def code_complexity(code: str) -> float:
        """L(H)——gzip后字节数近似Kolmogorov复杂度."""
        return float(len(gzip.compress(code.encode("utf-8"))))

    @staticmethod
    def error_cost(test_failures: int) -> float:
        """L(D|H)——测试失败的编码成本."""
        return float(test_failures) * 50.0  # 每个失败≈50字节

    def score(self, code: str, test_failures: int = 0) -> float:
        """MDL总分——越低越好."""
        return self.code_complexity(code) + self.error_cost(test_failures)

    @staticmethod
    def pareto_rank(candidates: list[dict]) -> list[int]:
        """Pareto前沿排序——正确性×简洁性.

        candidates: [{"code":..., "failures":0, "mdl":...}, ...]
        """
        scored = [(i, c["failures"], c.get("mdl", 0))
                  for i, c in enumerate(candidates)]
        # 非支配排序
        ranks = [0] * len(candidates)
        for i, (_, f_i, m_i) in enumerate(scored):
            dominated = sum(1 for _, f_j, m_j in scored
                           if f_j <= f_i and m_j <= m_i
                           and (f_j < f_i or m_j < m_i))
            ranks[i] = dominated
        return ranks
