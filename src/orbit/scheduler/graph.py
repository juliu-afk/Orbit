"""Step 5.1 DAG 任务图数据模型。

WHY DAG：MVP 状态机只支持串行单路径，软件开发任务（并行编码+验证）需要
有向无环图表达依赖关系，同层节点可并发执行，加速吞吐。

实现：Kahn 算法拓扑排序 + 邻接表循环检测。
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeStatus(StrEnum):
    """DAG 节点执行状态。

    WHY 独立于 TaskState：TaskState 是任务级状态，NodeStatus 是节点级。
    一个任务包含多个节点，各自有生命周期。
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class GraphNode(BaseModel):
    """DAG 节点：一个 Agent 执行单元。

    WHY input/output 用 dict：不同 Agent 角色输入输出 Schema 不同，
    dict 提供灵活性，Pydantic 模型在 Agent 层做强校验。
    """

    id: str
    agent_role: str = "developer"
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    status: NodeStatus = NodeStatus.PENDING
    retry_count: int = 0
    error: str | None = None


class TaskGraph(BaseModel):
    """DAG 任务图：节点集合 + 依赖边。

    edges 格式：[(source_id, target_id), ...]
    表示 source → target（source 完成后 target 才能开始）。
    """

    task_id: str
    nodes: list[GraphNode]
    edges: list[tuple[str, str]] = Field(default_factory=list)

    def validate_dag(self) -> None:
        """验证 DAG 合法性：无循环、边引用的节点存在。

        WHY 命名 validate_dag 而非 validate：
        BaseModel.validate 是 Pydantic 类方法（签名 def validate(cls, value: Any) -> TaskGraph），
        重名但签名不同导致 mypy override 错误。validate_dag 语义更精确。

        Raises:
            ValueError: 循环依赖或引用不存在的节点
        """
        node_ids = {n.id for n in self.nodes}
        # 边引用的节点必须存在
        for src, dst in self.edges:
            if src not in node_ids:
                raise ValueError(f"Edge source '{src}' not in nodes")
            if dst not in node_ids:
                raise ValueError(f"Edge target '{dst}' not in nodes")
        # 循环检测：拓扑排序节点数 < 总节点数 → 有环
        # P1 LOG-1: 空图 (0 nodes) 为合法 DAG——len(flat)==len(nodes) 均为 0，不抛异常
        try:
            order = self.topological_sort()
            flat = [nid for layer in order for nid in layer]
            if len(flat) != len(self.nodes):
                raise ValueError("DAG contains a cycle")
        except ValueError as e:
            if "cycle" in str(e).lower():
                raise
            raise ValueError(f"DAG validation failed: {e}") from e

    def topological_sort(self) -> list[list[str]]:
        """Kahn 算法分层拓扑排序。

        WHY 分层输出：同层节点无依赖，可并发执行。
        返回 [[layer0_ids], [layer1_ids], ...] 每层内部可并行。

        Raises:
            ValueError: 存在循环依赖
        """
        node_ids = {n.id for n in self.nodes}
        # 构建邻接表和入度
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        for src, dst in self.edges:
            if src in adj:
                adj[src].append(dst)
            if dst in in_degree:
                in_degree[dst] += 1

        # Kahn 算法：入度为 0 的节点入队
        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        layers: list[list[str]] = []
        visited_count = 0

        while queue:
            layer: list[str] = []
            for _ in range(len(queue)):
                nid = queue.popleft()
                layer.append(nid)
                visited_count += 1
                for neighbor in adj[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            layers.append(layer)

        if visited_count != len(self.nodes):
            raise ValueError(f"DAG cycle detected: {visited_count}/{len(self.nodes)} nodes sorted")
        return layers

    def get_node(self, node_id: str) -> GraphNode | None:
        """按 ID 查找节点。"""
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_dependencies(self, node_id: str) -> list[str]:
        """获取某节点的所有直接上游依赖。"""
        return [src for src, dst in self.edges if dst == node_id]

    def get_dependents(self, node_id: str) -> list[str]:
        """获取某节点的所有直接下游节点。"""
        return [dst for src, dst in self.edges if src == node_id]
