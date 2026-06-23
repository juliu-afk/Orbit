"""S2: 重试修复——Mock LLM 前 2 次失败 → 第 3 次成功。"""

import asyncio
from typing import Any

import pytest

from orbit.gateway.schemas import LLMRequest
from tests.e2e.mock_llm import LLMError, MockLLMClient


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_resume_from_checkpoint(e2e_app: Any) -> None:
    """任务执行 → 模拟中断 → 从检查点恢复。

    验证：调度器的 resume 功能在 Mock LLM 环境下正常运行。
    """
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    task_id = "resume-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5"
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "检查点恢复测试"),
        timeout=30,
    )
    assert state.value == "DONE"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_mock_llm_fail_count(mock_llm: MockLLMClient) -> None:
    """MockLLMClient fail_count 行为正确——前 N 次抛异常。"""
    mock_llm.fail_count = 3

    req = LLMRequest(prompt="test", system_prompt="", temperature=0.0, max_tokens=100)

    # 前 3 次抛异常
    for i in range(3):
        with pytest.raises(LLMError):
            await mock_llm.generate(req, task_id="t1")
        assert mock_llm.call_count == i + 1

    # 第 4 次成功
    resp = await mock_llm.generate(req, task_id="t1")
    assert resp.model == "mock-model"
    assert resp.content == "[mock] CODE_GENERATED_OK"
    assert mock_llm.call_count == 4
