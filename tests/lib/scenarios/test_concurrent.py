"""并发场景——多任务并行/DAG 分层执行/资源竞争。

验证 DAG 拓扑排序和并发执行的正确性。
"""

from __future__ import annotations

import pytest

from tests.lib.builders import DagChain


@pytest.mark.scenario_concurrent
async def test_dag_topological_order_5_nodes(scenario_mocks: dict) -> None:
    """5 节点 DAG，节点 2 和 3 依赖节点 1→验证拓扑序。"""
    chain = DagChain(mocks=scenario_mocks)
    await chain.with_nodes(5).with_dependencies({2: [1], 3: [1], 4: [2, 3], 5: [4]}).run()

    chain.assert_node_order()
    # 至少分 4 层（1 → 2,3 → 4 → 5）
    assert len(chain.layers) >= 4


@pytest.mark.scenario_concurrent
async def test_dag_independent_nodes_parallel(scenario_mocks: dict) -> None:
    """无依赖的 3 个节点→应在同一层并发执行。"""
    chain = DagChain(mocks=scenario_mocks)
    await chain.with_nodes(3).run()

    chain.assert_node_order()
    # 所有节点无依赖→在同一层
    assert len(chain.layers) == 1
    assert len(chain.layers[0]) == 3


@pytest.mark.scenario_concurrent
async def test_dag_all_nodes_succeed(scenario_mocks: dict) -> None:
    """无预设失败→所有节点正常完成。"""
    chain = DagChain(mocks=scenario_mocks)
    await chain.with_nodes(3).with_dependencies({2: [1], 3: [2]}).run()
    chain.assert_node_order()
    assert len(chain.results) == 3


@pytest.mark.scenario_concurrent
async def test_dag_preset_node_failure(scenario_mocks: dict) -> None:
    """预设节点失败→fail_fast 跳过下游。"""
    chain = DagChain(mocks=scenario_mocks)
    chain._node_results["node_2"] = {"status": "failed", "output": "mock failure"}
    chain._node_results["node_1"] = {"status": "ok", "output": "node 1 done"}
    await chain.with_nodes(3).with_dependencies({2: [1], 3: [2]}).run()
    chain.assert_node_order()
    chain.assert_node_failed("node_2")
    chain.assert_node_skipped("node_3")


@pytest.mark.scenario_concurrent
async def test_dag_cycle_detection(scenario_mocks: dict) -> None:
    """循环依赖（1→2→3→1）→抛出循环检测错误。"""
    chain = DagChain(mocks=scenario_mocks)

    with pytest.raises(ValueError, match="循环依赖"):
        chain.with_nodes(3).with_dependencies({1: [3], 2: [1], 3: [2]})
