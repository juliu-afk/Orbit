"""MDP 形式化 (V14.2+Theory 方向17).

形式化Agent循环为有限时域MDP——计算Bellman gap量化策略偏离最优程度.
离线分析层——不替换ReAct循环.

用法:
    mdp = AgentMDP(discount=0.95)
    gap = mdp.compute_bellman_gap(policy_fn, value_fn, transitions)
"""
from __future__ import annotations
import math


class AgentMDP:
    """Agent ReAct 循环的 MDP 形式化.

    S = (task_type, graph_snapshot, tool_history[:k], checkpoint_state)
    A = (generate_code, call_tool_X, escalate, wait, backtrack)
    R = 任务成功 - 成本
    """

    def __init__(self, discount: float = 0.95):
        self.gamma = discount

    def state_features(self, task_context: dict) -> list[float]:
        """状态特征向量——MDP状态空间的低维投影."""
        fc = float(task_context.get("file_count", 1))
        risk = {"low": 0.0, "medium": 0.5, "high": 1.0}.get(
            task_context.get("risk", "low"), 0.5)
        tools = min(float(task_context.get("tool_calls", 0)) / 20.0, 1.0)
        turns = min(float(task_context.get("turns", 0)) / 50.0, 1.0)
        budget = min(float(task_context.get("tokens_used", 0)) / 128000.0, 1.0)
        return [fc / 20.0, risk, tools, turns, budget]

    def reward(self, state: list[float], action: str,
               next_state: list[float], terminal: bool = False) -> float:
        """奖励函数——完成+1, 失败-1, 中间步骤负成本."""
        if terminal and next_state[3] > 0.8:  # turns near max
            return 1.0  # 完成
        if terminal:
            return -1.0  # 失败
        token_cost = 0.001 * action_cost(action)
        return -token_cost

    def compute_bellman_gap(self, transitions: list[dict]) -> float:
        """Bellman误差 = Σ|Q(s,a) - (r + γ max_a' Q(s',a'))|.

        gap→0 = 接近最优, gap大 = 有提升空间.
        P2-1修复: 值迭代估计V(s)后计算真实Bellman gap.
        """
        if not transitions:
            return 0.0
        # 值迭代估计V(s)——3轮够收敛
        V = {}
        for t in transitions:
            for key in ("s", "s_next"):
                sk = tuple(round(x, 2) for x in t[key][:3])
                V[sk] = 0.0
        for _ in range(3):
            V_new = dict(V)
            for t in transitions:
                sk = tuple(round(x, 2) for x in t["s"][:3])
                snk = tuple(round(x, 2) for x in t["s_next"][:3])
                V_new[sk] = max(V_new.get(sk, 0.0),
                                t["r"] + self.gamma * V.get(snk, 0.0))
            V = V_new
        total = 0.0
        for t in transitions:
            sk = tuple(round(x, 2) for x in t["s"][:3])
            snk = tuple(round(x, 2) for x in t["s_next"][:3])
            target = t["r"] + self.gamma * V.get(snk, 0.0)
            total += abs(V.get(sk, 0.0) - target)
        return total / len(transitions)


def action_cost(action: str) -> float:
    """估算动作Token成本."""
    costs = {"generate_code": 500, "call_tool": 200,
             "escalate": 100, "wait": 10, "backtrack": 50}
    return float(costs.get(action, 200))
