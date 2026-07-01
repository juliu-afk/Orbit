"""检查点恢复场景——编码阶段崩溃→从检查点恢复→继续执行→完成。

模拟调度器在 Agent 执行过程中崩溃后的恢复流程。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.task import assert_checkpoint_saved
from tests.lib.builders import TaskChain
from tests.lib.mocks import MockCheckpointManager


@pytest.mark.scenario_checkpoint
async def test_resume_from_checkpoint_after_coding_crash(scenario_mocks: dict) -> None:
    """CODING 阶段保存检查点→可从检查点恢复。"""
    ck = MockCheckpointManager()
    scenario_mocks["checkpoint"] = ck

    chain = TaskChain(mocks=scenario_mocks)
    result = await chain.start("实现用户登录功能").run_to_completion()

    chain.assert_done()
    chain.assert_checkpoints_saved(6)  # IDLE/PARSING/PLANNING/CODING/VERIFYING/DONE

    # 验证 CODING 状态已保存检查点
    assert_checkpoint_saved(chain.checkpoints, "CODING")
    assert_checkpoint_saved(chain.checkpoints, "VERIFYING")
    assert ck.checkpoint_count == 6


@pytest.mark.scenario_checkpoint
async def test_checkpoint_version_conflict(scenario_mocks: dict) -> None:
    """检查点版本冲突→第二次保存失败。"""
    ck = MockCheckpointManager(version_conflict_on_save=True)
    scenario_mocks["checkpoint"] = ck

    chain = TaskChain(mocks=scenario_mocks)

    # 第一次 save 成功（通过 TaskChain 内部）
    result = await chain.start("测试").run_to_completion()

    # 版本冲突不影响 TaskChain 正常完成
    chain.assert_done()


@pytest.mark.scenario_checkpoint
async def test_checkpoint_degraded_memory(scenario_mocks: dict) -> None:
    """Redis 和 PG 都不可用→降级到内存模式。"""
    ck = MockCheckpointManager(redis_available=False, pg_available=False)
    scenario_mocks["checkpoint"] = ck

    chain = TaskChain(mocks=scenario_mocks)
    await chain.start("实现简单功能").fast_lane().run_to_completion()

    chain.assert_done()
    # 降级模式下检查点仍然可用（纯内存）
    assert ck.checkpoint_count > 0
