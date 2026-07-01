"""图谱工厂——创建测试用 GraphNode 和 TaskGraph。

用于 DAG 构建器测试。
"""

from __future__ import annotations

import uuid
from typing import Any


def create_graph_node(
    node_id: str | None = None,
    description: str = "实现登录 API",
    agent_role: str = "developer",
    depends_on: list[str] | None = None,
    status: str = "PENDING",
    **kwargs: Any,
) -> dict[str, Any]:
    """创建 GraphNode dict——用于 DAG 节点定义。

    Args:
        node_id: 节点 ID（None→自动生成 UUID）
        description: 节点描述
        agent_role: 执行 Agent 角色
        depends_on: 依赖的节点 ID 列表
        status: 节点状态（PENDING/RUNNING/DONE/FAILED/SKIPPED）
    """
    if node_id is None:
        node_id = str(uuid.uuid4())

    return {
        "id": node_id,
        "description": description,
        "agent_role": agent_role,
        "depends_on": depends_on or [],
        "status": status,
        **kwargs,
    }


def create_dag_layers(
    layers: list[list[str]],
    prefix: str = "node",
) -> list[dict[str, Any]]:
    """创建分层 DAG 节点列表。

    每层内的节点无依赖关系（可并行），后层依赖前层所有节点。

    Args:
        layers: 每层的节点描述列表，如 [["解析需求"], ["设计A", "设计B"], ["实现"]]
        prefix: 节点 ID 前缀

    Returns:
        GraphNode dict 列表，已设置 depends_on 实现分层依赖
    """
    nodes = []
    prev_ids = []

    for layer_idx, descriptions in enumerate(layers):
        current_ids = []
        for node_idx, desc in enumerate(descriptions):
            nid = f"{prefix}_{layer_idx}_{node_idx}"
            nodes.append(create_graph_node(
                node_id=nid,
                description=desc,
                depends_on=list(prev_ids),  # 依赖上一层所有节点
                agent_role="developer" if layer_idx % 2 == 0 else "reviewer",
            ))
            current_ids.append(nid)
        prev_ids = current_ids

    return nodes
