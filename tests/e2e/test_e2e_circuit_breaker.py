"""S3: 熔断降级——Mock LLM 持续 5xx → 熔断器触发。"""

import asyncio

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.orchestrator import Scheduler
from tests.e2e.mock_llm import MockLLMClient


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_circuit_breaker_with_failing_llm(e2e_app):
    """LLM 全部失败 → 任务 FAILED + 熔断逻辑触发。

    AC3: 任务最终状态为 FAILED。
    """
    scheduler: Scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    # 创建一个 fail_count 极大的 MockLLM，确保所有 LLM 调用失败
    failing_llm = MockLLMClient(fail_count=999, fixed_response="should not reach")
    scheduler.llm = failing_llm

    task_id = "circuit-breaker-test-id-000000000"
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "熔断测试"),
        timeout=30,
    )
    # 所有 LLM 调用失败 → 任务应 FAILED
    assert state == TaskState.FAILED, f"期望 FAILED，实际 {state}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_circuit_breaker_recovers(e2e_app):
    """恢复正常的 LLM 后任务可成功。

    验证调度器在 LLM 恢复后能正常执行。
    """
    scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    # 恢复正常的 Mock LLM
    scheduler.llm = MockLLMClient(fail_count=0)

    task_id = "circuit-breaker-recovery-test-00000"
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "恢复测试"),
        timeout=30,
    )
    assert state == TaskState.DONE, f"期望 DONE，实际 {state}"
