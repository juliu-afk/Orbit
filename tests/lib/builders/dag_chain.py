"""DagChain——DAG 拓扑排序+分层并发构建器。

模拟 DagRunner 的 DAG 执行：拓扑排序→分层→每层并发→结果收集。
用于测试多任务编排和依赖管理。

使用示例:
    chain = DagChain()
    result = await chain.with_nodes(5).with_dependencies({2:[1], 3:[1]}).run()
    chain.assert_node_order()
"""

from __future__ import annotations

from collections import deque
from typing import Any

from tests.lib.factories.agent import create_agent_output
from tests.lib.factories.graph import create_graph_node
from tests.lib.mocks.llm_client import MockLLMClient
from tests.lib.mocks.sandbox import MockSandbox
from tests.lib.mocks.checkpoint import MockCheckpointManager
from tests.lib.mocks.event_bus import MockEventBus


class DagChain:
    """DAG 拓扑排序+分层并发构建器。

    模拟生产 DagRunner.run_dag() 的核心流程：
    1. 验证 DAG 无循环依赖
    2. Kahn 拓扑排序分层
    3. 同层节点并发执行
    4. 上游失败时 fail_fast
    """

    def __init__(self, mocks: dict[str, Any] | None = None) -> None:
        mocks = mocks or {}
        self.llm: MockLLMClient = mocks.get("llm", MockLLMClient())
        self.sandbox: MockSandbox = mocks.get("sandbox", MockSandbox())
        self.checkpoint: MockCheckpointManager = mocks.get("checkpoint", MockCheckpointManager())
        self.event_bus: MockEventBus = mocks.get("event_bus", MockEventBus())

        self._nodes: dict[str, dict[str, Any]] = {}
        self._fail_fast: bool = True
        self._node_results: dict[str, Any] = {}

        # 运行结果
        self.results: list[dict[str, Any]] = []
        self.execution_order: list[str] = []  # 实际执行顺序
        self.layers: list[list[str]] = []     # 拓扑分层结果

    # ── 链式配置 ──────────────────────────────────────────

    def with_nodes(self, count: int, descriptions: list[str] | None = None) -> "DagChain":
        """创建 N 个无依赖节点。

        Args:
            count: 节点数
            descriptions: 节点描述列表（长度必须 = count，None→自动生成）
        """
        self._nodes.clear()
        descs = descriptions or [f"Task {i}: auto-generated step" for i in range(1, count + 1)]
        if len(descs) != count:
            raise ValueError(f"descriptions length {len(descs)} != count {count}")

        for i in range(1, count + 1):
            nid = f"node_{i}"
            self._nodes[nid] = create_graph_node(
                node_id=nid,
                description=descs[i - 1],
                agent_role="developer" if i % 2 == 1 else "reviewer",
            )
        return self

    def with_dependencies(self, edges: dict[int, list[int]]) -> "DagChain":
        """设置依赖关系。

        Args:
            edges: {node_id: [depends_on_node_ids]} —— node_id 依赖 depends_on 中的节点

        Raises:
            ValueError: 循环依赖检测到时
        """
        for nid, deps in edges.items():
            node_key = f"node_{nid}"
            if node_key not in self._nodes:
                self._nodes[node_key] = create_graph_node(node_id=node_key)
            self._nodes[node_key]["depends_on"] = [f"node_{d}" for d in deps]

        # 循环依赖检测 (Kahn 算法)
        self._validate_no_cycles()
        return self

    def fail_fast(self, enabled: bool = True) -> "DagChain":
        """设置 fail_fast 模式。"""
        self._fail_fast = enabled
        return self

    def with_node_results(self, results: dict[str, Any]) -> "DagChain":
        """预设节点的执行结果。"""
        self._node_results = results
        return self

    # ── 执行 ──────────────────────────────────────────────

    async def run(self) -> list[dict[str, Any]]:
        """执行 DAG：拓扑排序→分层→并发。

        Returns:
            每个节点的执行结果列表 [{node_id, status, output, layer}]
        """
        if not self._nodes:
            raise ValueError("No nodes defined. Call with_nodes() first.")

        # 拓扑排序 + 分层
        self.layers = self._topological_sort_layers()

        self.results = []

        for layer_idx, layer in enumerate(self.layers):
            # 同层节点并发执行（简化：顺序执行 + 收集）
            layer_results = []
            for nid in layer:
                result = await self._execute_node(nid, layer_idx)
                layer_results.append(result)
                self.execution_order.append(nid)

                # fail_fast: 上游失败→标记下游跳过
                if result["status"] == "failed" and self._fail_fast:
                    self._skip_downstream(nid, layer_idx)
                    self.results.extend(layer_results)
                    return self.results

            self.results.extend(layer_results)

        return self.results

    async def _execute_node(self, nid: str, layer: int) -> dict[str, Any]:
        """执行单个节点——调用 Mock LLM + 沙箱。"""
        node = self._nodes.get(nid, {})

        # 使用预设结果（dict含status=用作结果；其他=包裹为ok）
        if nid in self._node_results:
            result = self._node_results[nid]
            if isinstance(result, dict) and "status" in result:
                result.setdefault("node_id", nid)
                result.setdefault("layer", layer)
                return result
            return {"node_id": nid, "status": "ok", "output": str(result), "layer": layer}

        # 模拟 Agent 执行
        try:
            # 模拟 LLM 调用
            from tests.lib.factories.llm import create_llm_request

            req = create_llm_request(prompt=node.get("description", f"Execute {nid}"))
            llm_resp = await self.llm.generate(req, task_id=nid, agent_name=node.get("agent_role", "developer"))

            # 模拟沙箱执行
            await self.sandbox.run(llm_resp.content)

            # 保存检查点
            from tests.lib.factories.checkpoint import create_checkpoint

            cp = create_checkpoint(task_id=nid, state="DONE")
            await self.checkpoint.save(nid, cp)

            # 发布事件
            self.event_bus.publish({"type": "dag:node_complete", "node_id": nid, "layer": layer})

            return {
                "node_id": nid,
                "status": "ok",
                "output": llm_resp.content,
                "layer": layer,
                "turns": 1,
                "tool_calls": 0,
            }
        except Exception as e:
            return {"node_id": nid, "status": "failed", "output": str(e), "layer": layer}

    def _skip_downstream(self, failed_nid: str, failed_layer: int) -> None:
        """fail_fast 模式下标记下游节点为 SKIPPED。"""
        for layer_idx in range(failed_layer + 1, len(self.layers)):
            for nid in self.layers[layer_idx]:
                self.results.append({
                    "node_id": nid,
                    "status": "skipped",
                    "output": f"上游节点 {failed_nid} 失败，跳过",
                    "layer": layer_idx,
                })

    # ── 拓扑排序 ──────────────────────────────────────────

    def _topological_sort_layers(self) -> list[list[str]]:
        """Kahn 算法拓扑排序，输出分层列表。

        Returns:
            [[layer0_nodes], [layer1_nodes], ...] 每层内节点可并行
        """
        # 计算入度
        in_degree: dict[str, int] = {}
        adj: dict[str, list[str]] = {}

        for nid in self._nodes:
            in_degree[nid] = 0
            adj[nid] = []

        for nid, node in self._nodes.items():
            for dep in node.get("depends_on", []):
                if dep in self._nodes:
                    in_degree[nid] = in_degree.get(nid, 0) + 1
                    adj.setdefault(dep, []).append(nid)

        # Kahn 分层
        queue: deque[str] = deque()
        for nid, deg in in_degree.items():
            if deg == 0:
                queue.append(nid)

        layers: list[list[str]] = []
        visited: set[str] = set()

        while queue:
            layer: list[str] = []
            for _ in range(len(queue)):
                nid = queue.popleft()
                if nid in visited:
                    continue
                visited.add(nid)
                layer.append(nid)
                for neighbor in adj.get(nid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            if layer:
                layers.append(layer)

        return layers

    def _validate_no_cycles(self) -> None:
        """Kahn 算法检测循环依赖。

        Raises:
            ValueError: 存在循环依赖时
        """
        in_degree: dict[str, int] = {}
        adj: dict[str, list[str]] = {}

        for nid in self._nodes:
            in_degree[nid] = 0
            adj[nid] = []

        for nid, node in self._nodes.items():
            for dep in node.get("depends_on", []):
                if dep in self._nodes:
                    in_degree[nid] = in_degree.get(nid, 0) + 1
                    adj.setdefault(dep, []).append(nid)

        queue = deque([n for n in self._nodes if in_degree.get(n, 0) == 0])
        visited_count = 0

        while queue:
            nid = queue.popleft()
            visited_count += 1
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self._nodes):
            unvisited = [n for n in self._nodes if in_degree.get(n, 0) > 0]
            raise ValueError(f"循环依赖检测: {len(self._nodes) - visited_count} 个节点不可达: {unvisited}")

    # ── 断言 ──────────────────────────────────────────────

    def assert_node_order(self) -> None:
        """验证执行顺序符合拓扑序。"""
        # 每层的节点必须在依赖的节点之后执行
        node_pos = {nid: i for i, nid in enumerate(self.execution_order)}
        for nid, node in self._nodes.items():
            for dep in node.get("depends_on", []):
                if dep in node_pos and nid in node_pos:
                    assert node_pos[dep] < node_pos[nid], (
                        f"节点 {nid} 在依赖 {dep} 之前执行: {self.execution_order}"
                    )

    def assert_layer_concurrency(self, min_per_layer: int = 1) -> None:
        """验证分层至少有基本的结构。"""
        assert len(self.layers) >= 1, "DAG 无分层"
        for i, layer in enumerate(self.layers):
            assert len(layer) >= min_per_layer, f"Layer {i} 无节点"

    def assert_node_failed(self, node_id: str) -> None:
        """断言指定节点失败。"""
        for r in self.results:
            if r["node_id"] == node_id:
                assert r["status"] == "failed", f"节点 {node_id} 状态应为 'failed'，实际: {r['status']}"
                return
        raise AssertionError(f"节点 {node_id} 未在执行结果中找到")

    def assert_node_skipped(self, node_id: str) -> None:
        """断言指定节点被跳过（fail_fast）。"""
        for r in self.results:
            if r["node_id"] == node_id:
                assert r["status"] == "skipped", f"节点 {node_id} 应被跳过，实际: {r['status']}"
                return
        raise AssertionError(f"节点 {node_id} 未在执行结果中找到")

    def reset(self) -> None:
        self._nodes.clear()
        self._node_results.clear()
        self.results.clear()
        self.execution_order.clear()
        self.layers.clear()
