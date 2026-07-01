"""Task 工厂——创建测试用 Task 数据。

Task 对应 compose/models.py 中的 Task 模型，用于 DAG 节点和任务定义。
"""

from __future__ import annotations

import uuid
from typing import Any


def create_task(
    task_id: str | None = None,
    description: str = "测试任务：实现用户登录功能",
    agent_role: str = "developer",
    skill: str = "",
    depends_on: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """创建 Task dict——兼容 compose/models.py:Task 字段。

    Args:
        task_id: 任务 ID（None→自动生成 UUID）
        description: 任务描述
        agent_role: 执行 Agent 角色（developer/architect/reviewer/qa/config_manager/clarifier）
        skill: 使用的技能名称
        depends_on: 依赖的任务 ID 列表
    """
    if task_id is None:
        task_id = str(uuid.uuid4())

    task = {
        "id": task_id,
        "description": description,
        "agent_role": agent_role,
        "skill": skill,
        "depends_on": depends_on or [],
    }
    task.update(kwargs)
    return task


def create_task_graph(
    node_count: int = 3,
    prefix: str = "task",
) -> dict[str, dict[str, Any]]:
    """创建简单任务图（无依赖关系）。

    Args:
        node_count: 节点数
        prefix: 任务 ID 前缀

    Returns:
        {task_id: task_dict} 映射
    """
    tasks = {}
    for i in range(1, node_count + 1):
        tid = f"{prefix}_{i}"
        tasks[tid] = create_task(
            task_id=tid,
            description=f"Task {i}: 执行代码生成步骤 {i}",
            agent_role="developer" if i % 2 == 1 else "reviewer",
        )
    return tasks


def create_task_graph_with_deps(
    edges: dict[int, list[int]],
    prefix: str = "task",
) -> dict[str, dict[str, Any]]:
    """创建带依赖关系的任务图。

    Args:
        edges: {node_id: [dependent_node_ids]} 依赖映射
        prefix: 任务 ID 前缀

    Returns:
        {task_id: task_dict} 映射
    """
    tasks = {}
    all_ids = set(edges.keys()) | {d for deps in edges.values() for d in deps}

    for nid in sorted(all_ids):
        tid = f"{prefix}_{nid}"
        deps = [f"{prefix}_{d}" for d in edges.get(nid, [])]
        tasks[tid] = create_task(
            task_id=tid,
            description=f"Task {nid}",
            depends_on=deps,
        )
    return tasks
