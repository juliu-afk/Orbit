"""DagRunner——DAG 编排执行器（内部减熵 P1）.

从 Scheduler 拆出: run_dag / resume_dag / _execute_layer /
_execute_node_with_retry / _execute_node / _save_dag_checkpoint.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.events.bus import EventBus
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload
from orbit.scheduler.graph import GraphNode, NodeStatus, TaskGraph

logger = structlog.get_logger()


class DagRunner:
    """DAG 编排——拓扑排序→分层并发执行 + 检查点/事件.

    用法:
        runner = DagRunner(
            checkpoint=checkpoint, event_bus=event_bus,
            max_concurrent=3, node_timeout=30, max_retries=2, fail_fast=True,
        )
        results = await runner.run_dag(graph)
    """

    def __init__(
        self,
        *,
        checkpoint: CheckpointManager | None = None,
        event_bus: EventBus | None = None,
        max_concurrent: int = 3,
        node_timeout: int = 30,
        max_retries: int = 2,
        fail_fast: bool = True,
    ) -> None:
        self.checkpoint = checkpoint
        self._event_bus = event_bus
        self._max_concurrent = max_concurrent
        self._node_timeout = node_timeout
        self._max_retries = max_retries
        self._fail_fast = fail_fast

    # ── 公共入口 ────────────────────────────────────────

    async def run_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        """DAG 入口: 验证→拓扑排序→分层并发执行."""
        graph.validate_dag()
        layers = graph.topological_sort()
        logger.info(
            "dag_execution_start",
            task_id=graph.task_id,
            nodes=len(graph.nodes),
            layers=len(layers),
        )

        for layer_idx, layer in enumerate(layers):
            logger.info(
                "dag_layer_executing", task_id=graph.task_id, layer=layer_idx, node_count=len(layer)
            )
            await self._execute_layer(graph, layer)
            if self._fail_fast and any(
                (n := graph.get_node(nid)) and n.status == NodeStatus.FAILED for nid in layer
            ):
                logger.warning("dag_fail_fast_abort", task_id=graph.task_id)
                break

        results = {n.id: n.status for n in graph.nodes}
        logger.info("dag_execution_complete", task_id=graph.task_id, results=results)
        return results

    async def resume_dag(self, graph: TaskGraph) -> dict[str, NodeStatus]:
        """从检查点恢复 DAG——跳过 SUCCESS, 重置 RUNNING/FAILED."""
        for node in graph.nodes:
            if node.status == NodeStatus.SUCCESS:
                continue  # P0-2: 跳过已成功节点
            if node.status == NodeStatus.RUNNING:
                node.status = NodeStatus.PENDING
            elif node.status == NodeStatus.FAILED:
                node.retry_count = 0
                node.error = None  # P2-15: 重置错误信息
                node.status = NodeStatus.PENDING

        logger.info("dag_resume", task_id=graph.task_id)
        return await self.run_dag(graph)

    # ── 内部 ────────────────────────────────────────────

    async def _execute_layer(self, graph: TaskGraph, layer: list[str]) -> None:
        """并发执行一层中所有节点.

        P0-3: 跳过上游依赖已失败的节点——不需要执行下游.
        """
        sem = asyncio.Semaphore(self._max_concurrent)

        async def _run_one(nid: str) -> None:
            async with sem:
                node = graph.get_node(nid)
                if node is None:
                    logger.warning("dag_node_not_found", node_id=nid)  # P2-13
                    return
                # P0-3: 检查上游依赖——任何上游失败则跳过
                if not self._fail_fast:
                    upstream_failed = any(
                        (up := graph.get_node(dep_id)) and up.status == NodeStatus.FAILED
                        for dep_id in getattr(node, "depends_on", [])
                    )
                    if upstream_failed:
                        node.status = NodeStatus.SKIPPED
                        logger.info("dag_node_skipped_upstream_failed", node_id=nid)
                        self._publish_dag_update(graph)
                        return
                await self._execute_node_with_retry(graph, node)

        tasks = [_run_one(nid) for nid in layer]
        await asyncio.gather(*tasks)

    async def _execute_node_with_retry(self, graph: TaskGraph, node: GraphNode) -> None:
        """执行单节点——含超时和重试."""
        node.status = NodeStatus.RUNNING
        await self._save_dag_checkpoint(graph)
        self._publish_dag_update(graph)

        for attempt in range(self._max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_node(node), timeout=self._node_timeout
                )
                node.output = result
                node.status = NodeStatus.SUCCESS
                node.error = None
                await self._save_dag_checkpoint(graph)
                self._publish_dag_update(graph)
                return
            except TimeoutError:  # P1-6: 兼容 Python <3.11
                node.error = f"Timeout after {self._node_timeout}s (attempt {attempt+1})"
                logger.warning("dag_node_timeout", node=node.id, attempt=attempt + 1)
            except asyncio.CancelledError:
                raise  # P0-1: 不吞取消信号
            except Exception as e:
                node.error = str(e)
                logger.warning("dag_node_failed", node=node.id, error=str(e))

            node.retry_count = attempt + 1

        node.status = NodeStatus.FAILED
        await self._save_dag_checkpoint(graph)
        self._publish_dag_update(graph)
        logger.error("dag_node_all_retries_exhausted", node=node.id)

    async def _execute_node(self, node: GraphNode) -> dict[str, Any]:
        """执行单个节点的 Agent 逻辑."""
        # P2-12: TODO(#92) — Step 5.2 接入 AgentFactory 后根据 agent_role 路由到具体 Agent
        await asyncio.sleep(0.01)
        return {"status": "ok", "node": node.id, "role": node.agent_role}

    async def _save_dag_checkpoint(self, graph: TaskGraph) -> None:
        """保存 DAG 检查点."""
        if self.checkpoint is None:
            return
        try:
            snapshot = {
                "task_id": graph.task_id,
                "nodes": [
                    {
                        "id": n.id,
                        "status": n.status.value,
                        "retry_count": n.retry_count,
                        "error": n.error,
                        "output": n.output,  # P2-14: 保存节点输出
                    }
                    for n in graph.nodes
                ],
            }
            # P1-8: 计算实际完成进度
            total = len(graph.nodes)
            completed = sum(1 for n in graph.nodes if n.status == NodeStatus.SUCCESS)
            progress = completed / total if total > 0 else 0.0
            data = CheckpointData(
                task_id=graph.task_id,
                state="DAG_RUNNING",
                retry_count=0,
                progress=progress,
                context=snapshot,
                version=1,
            )
            await self.checkpoint.save(graph.task_id, data)
        except Exception as e:
            logger.warning("dag_checkpoint_save_failed", error=str(e))

    def _publish_dag_update(self, graph: TaskGraph) -> None:
        """发布 DAG 状态快照.

        P1-7: 同步方法——当前 EventBus.publish 是纯内存操作无 I/O,
        保持 sync 签名。若未来 publish 需 I/O 则改为 async.
        """
        if self._event_bus is None:
            return
        dag_nodes = [
            {
                "id": n.id,
                "agent_role": n.agent_role,
                "status": n.status.value,
                "duration_ms": None,
                "error": n.error,
            }
            for n in graph.nodes
        ]
        self._event_bus.publish(
            DashboardEvent(
                type="task:update",
                task_id=graph.task_id,
                payload=TaskUpdatePayload(
                    task_id=graph.task_id,
                    state="DAG_RUNNING",
                    progress=0.0,
                    dag=dag_nodes,
                    timestamp=datetime.now(UTC).isoformat(),
                ).model_dump(),
            )
        )
