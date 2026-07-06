"""MetaOrchestrator 工具函数——从 meta_orchestrator.py 拆分。"""
from __future__ import annotations
from datetime import UTC, datetime
from typing import Any
import structlog
from orbit.goal.models import GoalResult, GoalSession
logger = structlog.get_logger("orbit.goal")


def _generate_batch_report(results: list[GoalResult]) -> str:
    """生成批量执行报告。"""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
    path = f"docs/goal-report-{timestamp}.md"
    logger.info("batch_report_generated", path=path, count=len(results))
    return path

def _resolve_bases(
    layer: list[Any],
    previous_merges: dict[str, str],
) -> dict[str, str]:
    """P1-1: 确定每个 task 的 base_ref。"""
    bases = {}
    for t in layer:
        if not t.depends_on:
            bases[t.id] = "main"
        else:
            dep_shas = [previous_merges[d] for d in t.depends_on if d in previous_merges]
            if not dep_shas:
                bases[t.id] = "main"
            else:
                bases[t.id] = dep_shas[-1]
    return bases

def _topological_layers(tasks: list[Any]) -> list[list[Any]]:
    """Kahn 算法按层分组。"""
    task_map = {t.id: t for t in tasks}
    in_degree = {t.id: len(t.depends_on) for t in tasks}
    adj: dict[str, list[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        for dep in t.depends_on:
            if dep in adj:
                adj[dep].append(t.id)

    layers = []
    current = [t for t in tasks if in_degree[t.id] == 0]
    while current:
        layers.append(current)
        nxt = []
        for t in current:
            for neighbor in adj.get(t.id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    nxt.append(task_map[neighbor])
        current = nxt

    if sum(len(l) for l in layers) != len(tasks):
        remaining = {t.id for t in tasks} - {t.id for l in layers for t in l}
        raise ValueError(f"环形依赖或不可达节点: {remaining}")
    return layers

def _deserialize_spec(spec_data: dict) -> Any:
    """反序列化 Spec——兼容 dict 和 pydantic。"""
    try:
        from orbit.compose.models import Spec, Task

        return Spec(**spec_data)
    except Exception as e:
        logger.warning("spec_deserialize_failed", error=str(e)[:200])
        return spec_data

def _parse_to_goal(doc: dict) -> GoalSession:
    """批量文档转 GoalSession。"""
    return GoalSession(
        description=doc.get("description", "") or "Untitled Goal",
        constraints=doc.get("constraints", []),
        verification_commands=doc.get("verification_commands", []),
    )
