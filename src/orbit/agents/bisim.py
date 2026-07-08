"""互模拟 (V14.2+Theory 方向19).

P2-5修复: 逐状态最佳匹配而非全Cartesian积.
"""
from __future__ import annotations

class BisimulationChecker:
    def bisimilarity_score(self, lts_a: dict, lts_b: dict) -> float:
        """比较两个LTS的行为等价程度."""
        if not lts_a or not lts_b:
            return 0.0
        # 对A中每状态找B中最佳匹配→均值
        scores = []
        for sa, ta in lts_a.items():
            best = max((self._state_sim(ta, lts_b.get(sb, {}))
                        for sb in lts_b), default=0.0)
            scores.append(best)
        return sum(scores) / len(scores) if scores else 0.0

    @staticmethod
    def _state_sim(ta: dict, tb: dict) -> float:
        """两状态转移结构相似度——Jaccard+目标匹配."""
        acts = set(ta.keys()) | set(tb.keys())
        if not acts:
            return 1.0
        matches = 0
        for a in acts:
            in_a = a in ta
            in_b = a in tb
            if in_a and in_b:
                # 共享动作→检查转移目标是否相同
                matches += 1.0 if ta[a] == tb[a] else 0.5
            elif not in_a and not in_b:
                matches += 1.0
        return matches / len(acts)

    @staticmethod
    def is_replaceable(score: float, cost_a: float, cost_b: float,
                       threshold: float = 0.9) -> tuple[bool, str]:
        if score >= threshold:
            cheaper = "A" if cost_a < cost_b else "B"
            return (True, f"策略{cheaper}成本更低, bisim={score:.2f}")
        return (False, f"不等价(bisim={score:.2f}<{threshold})")
