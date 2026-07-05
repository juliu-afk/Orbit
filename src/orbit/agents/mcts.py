"""MCTS 多路径探索 (Phase D2).

对标: Tree-of-Thought, MCTS——探索多条推理路径，避免单路径死胡同

WHY:
  Orbit 当前规划是线性的——单路径 Thought→Action→Observation→...
  复杂场景（舞弊风险评估、多方案审计程序选择）需要多条路径并行探索。
  MCTS 用蒙特卡洛树搜索选择最有前景的路径。

设计:
  - 轻量级 MCTS——不需要完整游戏树，只需展开 2-3 层
  - 每个节点是一个 (goal_fragment, action) 对
  - UCB1 选择策略
  - 回传奖励: GoalJudge 评分 + Reflection confidence
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class MCTSNode:
    """MCTS 树节点——一个候选 Action。"""
    action: str = ""
    args: dict | None = None
    parent: MCTSNode | None = None
    children: list[MCTSNode] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0       # 累积奖励
    prior: float = 1.0        # 先验概率（LLM 给的初始置信度）
    depth: int = 0
    goal_fragment: str = ""   # 此节点要解决的子目标

    @property
    def avg_value(self) -> float:
        return self.value / max(self.visits, 1)

    def ucb1(self, exploration: float = 1.414) -> float:
        """UCB1 选择——平衡探索与利用。"""
        if self.visits == 0:
            return float("inf")
        return self.avg_value + exploration * math.sqrt(
            math.log(self.parent.visits) / self.visits
        ) if self.parent and self.parent.visits > 0 else self.avg_value


class MCTSPlanner:
    """MCTS 多路径规划器——对复杂目标展开多条候选路径。

    用法:
        planner = MCTSPlanner()
        root = planner.create_root(goal="评估舞弊风险")
        for _ in range(10):  # 10 次模拟
            node = planner.select(root)
            if not node.children or node.visits > 0:
                node = planner.expand(node, candidates)
            reward = await evaluate(node)  # 外部评估
            planner.backpropagate(node, reward)
        best = planner.best_path(root)
    """

    MAX_DEPTH = 3       # 最多展开 3 层
    EXPLORATION = 1.414  # UCB1 探索参数

    def create_root(self, goal: str) -> MCTSNode:
        return MCTSNode(action="root", goal_fragment=goal)

    def select(self, node: MCTSNode) -> MCTSNode:
        """选择——沿 UCB1 最高分值向下遍历，直到叶子节点。"""
        while node.children and node.visits > 0:
            node = max(node.children, key=lambda n: n.ucb1(self.EXPLORATION))
        return node

    def expand(self, node: MCTSNode, candidates: list[dict]) -> MCTSNode:
        """展开——为节点添加候选子节点。"""
        if node.depth >= self.MAX_DEPTH:
            return node
        for c in candidates[:5]:  # 最多 5 个候选
            child = MCTSNode(
                action=c.get("action", ""),
                args=c.get("args"),
                parent=node,
                depth=node.depth + 1,
                goal_fragment=c.get("goal_fragment", node.goal_fragment),
                prior=c.get("confidence", 80) / 100,
            )
            node.children.append(child)
        # 随机选一个子节点返回（首次访问用先验概率加权）
        if node.children:
            weights = [c.prior for c in node.children]
            total = sum(weights)
            r = random.random() * total
            acc = 0.0
            for c in node.children:
                acc += c.prior
                if r <= acc:
                    return c
            return node.children[0]
        return node

    def backpropagate(self, node: MCTSNode, reward: float) -> None:
        """回传——将奖励沿树向上传播。"""
        while node is not None:
            node.visits += 1
            node.value += reward
            node = node.parent

    def best_path(self, root: MCTSNode) -> list[MCTSNode]:
        """提取最优路径——沿最高 avg_value 向下。"""
        path = [root]
        node = root
        while node.children:
            node = max(node.children, key=lambda n: n.avg_value)
            path.append(node)
        return path

    def best_action(self, root: MCTSNode) -> MCTSNode | None:
        """最优下一步 Action。"""
        if not root.children:
            return None
        return max(root.children, key=lambda n: n.avg_value)
