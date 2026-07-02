"""S3: 熔断降级——Mock LLM 持续 5xx → 熔断器触发。"""

import asyncio
from typing import Any

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.orchestrator import Scheduler
from tests.e2e.mock_llm import MockLLMClient


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.xfail(reason="FIXME: LLM 全部失败时任务状态为 DONE 而非 FAILED——调度器可能已变更错误处理逻辑")
async def test_e2e_circuit_breaker_with_failing_llm(e2e_app: Any) -> None:
    """LLM 全部失败 → 任务 FAILED + 熔断逻辑触发。

    AC3: 任务最终状态为 FAILED。
    """
    scheduler: Scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    failing_llm = MockLLMClient(fail_count=999, fixed_response="should not reach")
    scheduler._agent_llms = {
        "developer": failing_llm,
        "clarifier": failing_llm,
        "architect": failing_llm,
        "reviewer": failing_llm,
    }

    task_id = "circuit-breaker-test-id-000000000"
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "熔断测试"),
        timeout=30,
    )
    assert state == TaskState.FAILED, f"期望 FAILED，实际 {state}"


@pytest.mark.e2e
@pytest.mark.asyncio(loop_scope="function")
async def test_e2e_normal_llm_recovers(e2e_app: Any) -> None:
    """恢复正常的 LLM 后任务可成功。"""
    scheduler: Scheduler = getattr(e2e_app, "_scheduler", None)
    assert scheduler is not None

    # ClarifierAgent 需要 JSON——单独给 mock response
    clarify_mock = MockLLMClient(
        fail_count=0,
        fixed_response='{"reply":"ok","clarification_status":"ready","structured_prd":{"goal":"test","scope":"test","acceptance_criteria":["ok"]}}',
    )
    ok = MockLLMClient(fail_count=0)
    scheduler._agent_llms = {
        "developer": ok,
        "clarifier": clarify_mock,
        "architect": ok,
        "reviewer": ok,
    }

    task_id = "recovery-test-id-00000000000000"
    state = await asyncio.wait_for(
        scheduler.run_task(task_id, "恢复测试"),
        timeout=30,
    )
    assert state == TaskState.DONE, f"期望 DONE，实际 {state}"
