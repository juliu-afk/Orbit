"""互模拟 (V14.2+Theory 方向19).

两个Agent策略→标号迁移系统→bisimilarity评分→等价者选低成本.
标号: 工具调用(action name), 状态: 任务上下文.

用法:
    checker = BisimulationChecker()
    score = checker.bisimilarity_score(lts_a, lts_b)
    if score > 0.9:  # 可互换
"""
from __future__ import annotations


class BisimulationChecker:
    """Agent策略行为等价检查器——标号迁移系统互模拟."""

    def bisimilarity_score(self, lts_a: dict, lts_b: dict) -> float:
        """计算两个LTS的逼近bisimilarity评分(0-1).

        lts: {state: {action: next_state, ...}, ...}
        """
        if not lts_a or not lts_b:
            return 0.0
        # 收集所有标号
        actions_a = set()
        actions_b = set()
        for s, trans in lts_a.items():
            actions_a.update(trans.keys())
        for s, trans in lts_b.items():
            actions_b.update(trans.keys())
        all_actions = actions_a | actions_b
        if not all_actions:
            return 1.0
        # 对每对标号检查转移是否匹配
        matches = 0
        for action in all_actions:
            in_a = action in actions_a
            in_b = action in actions_b
            if in_a and in_b:
                matches += 1
            elif in_a == in_b:  # 都不在
                matches += 1
        return matches / len(all_actions)

    @staticmethod
    def is_replaceable(score: float, cost_a: float, cost_b: float,
                       threshold: float = 0.9) -> tuple[bool, str]:
        """基于bisimilarity评分和成本决定是否可替换.

        Returns: (可替换?, 原因)
        """
        if score >= threshold:
            if cost_a < cost_b:
                return (True, f"策略A成本更低({cost_a}<{cost_b}), bisim={score:.2f}")
            else:
                return (True, f"策略B成本更低({cost_b}<{cost_a}), bisim={score:.2f}")
        return (False, f"不等价(bisim={score:.2f}<{threshold})")
