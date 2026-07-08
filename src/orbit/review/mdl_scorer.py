"""最小描述长度评分 (V14.2+Theory 方向7). P2-2修复: pareto_frontier分层."""
from __future__ import annotations
import gzip

class MDLScorer:
    @staticmethod
    def code_complexity(code: str) -> float:
        return float(len(gzip.compress(code.encode("utf-8"))))

    @staticmethod
    def error_cost(test_failures: int) -> float:
        return float(test_failures) * 50.0

    def score(self, code: str, test_failures: int = 0) -> float:
        return self.code_complexity(code) + self.error_cost(test_failures)

    @staticmethod
    def pareto_frontier(candidates: list[dict]) -> list[list[int]]:
        """P2-2修复: NSGA-II风格递归前沿分层(替代支配计数)."""
        n = len(candidates)
        dominated_by = [0] * n
        dominates = [[] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j: continue
                fi, mi = candidates[i].get("failures", 0), candidates[i].get("mdl", 0)
                fj, mj = candidates[j].get("failures", 0), candidates[j].get("mdl", 0)
                if fi <= fj and mi <= mj and (fi < fj or mi < mj):
                    dominates[i].append(j)
                elif fj <= fi and mj <= mi and (fj < fi or mj < mi):
                    dominated_by[i] += 1
        fronts = []
        remaining = set(range(n))
        while remaining:
            front = [i for i in remaining if dominated_by[i] == 0]
            if not front: break
            fronts.append(front)
            for i in front:
                remaining.discard(i)
                for j in dominates[i]:
                    dominated_by[j] -= 1
        return fronts
