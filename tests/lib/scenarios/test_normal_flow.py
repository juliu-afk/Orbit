"""正常流程场景——用户提交需求→系统自动实现→验证通过。

覆盖完整 IDLE→DONE 全链路。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.task import assert_state_transition
from tests.lib.builders import TaskChain


@pytest.mark.scenario_normal
async def test_normal_task_flow(scenario_mocks: dict) -> None:
    """用户提交需求→自动实现→验证通过。完整 IDLE→DONE。"""
    chain = TaskChain(mocks=scenario_mocks)
    result = await chain.start("实现用户登录功能——POST /auth/login，返回JWT token").run_to_completion()

    chain.assert_done()
    assert result.status == "ok"
    assert len(chain.state_history) >= 5  # 至少 IDLE→...→DONE

    # 验证状态转换序列
    assert_state_transition(chain.state_history, "IDLE", "PARSING")
    assert_state_transition(chain.state_history, "CODING", "VERIFYING")
    assert_state_transition(chain.state_history, "VERIFYING", "DONE")


@pytest.mark.scenario_normal
async def test_fast_lane_simple_task(scenario_mocks: dict) -> None:
    """简单任务走快车道：跳过 PLANNING 和 VERIFYING。"""
    chain = TaskChain(mocks=scenario_mocks)
    await chain.start("修复 typo——把 login 改成 log_in").fast_lane().run_to_completion()

    chain.assert_done()
    assert "PLANNING" not in chain.state_history
    assert "VERIFYING" not in chain.state_history
    assert "DONE" in chain.state_history
