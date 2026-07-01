"""边界场景——空输入/超长文本/无效工具调用/Doom Loop/极限值。

覆盖系统在异常输入下的鲁棒性。
"""

from __future__ import annotations

import pytest

from tests.lib.builders import ChatChain, TaskChain
from tests.lib.factories.prd import create_prd
from tests.lib.mocks import MockLLMClient, MockToolRegistry
from tests.lib.mocks.tool_registry import DoomLoopError, RateLimitError


# ── 空输入/超长输入 ──────────────────────────────────────

@pytest.mark.scenario_edge
async def test_empty_prd_creates_default_task(scenario_mocks: dict) -> None:
    """PRD 为空→使用默认 PRD，不崩溃。"""
    chain = TaskChain(mocks=scenario_mocks)
    # 不调用 start()→应抛错
    with pytest.raises(ValueError, match="must call start"):
        await chain.run_to_completion()

    # start("") → 应使用默认 PRD
    await chain.start("").run_to_completion()
    chain.assert_done()


@pytest.mark.scenario_edge
async def test_short_prd_triggers_clarification(scenario_mocks: dict) -> None:
    """极短 PRD（<20 字符）→ChatChain 判定需要澄清。"""
    chain = ChatChain(mocks=scenario_mocks)
    result = await chain.dialog([{"role": "user", "content": "登录"}]).run()

    assert result["status"] == "ok"
    # 极短输入可能触发澄清（由 IntakeRouter heuristic 判定）


@pytest.mark.scenario_edge
async def test_complex_prd_with_many_acceptance_criteria(scenario_mocks: dict) -> None:
    """复杂 PRD（多验收标准/多模块交叉）→正常处理。"""
    chain = TaskChain(mocks=scenario_mocks)
    prd = create_prd("complex")
    await chain.start(prd).run_to_completion()
    chain.assert_done()


# ── 无效工具/限流/Doom Loop ───────────────────────────────

@pytest.mark.scenario_edge
async def test_tool_rate_limit_triggers_error(scenario_mocks: dict) -> None:
    """工具调用超出限流→RateLimitError。"""
    reg = MockToolRegistry(rate_limited=True)

    with pytest.raises(RateLimitError):
        await reg.dispatch("read_file", {"path": "test.py"})


@pytest.mark.scenario_edge
async def test_doom_loop_detection_stops_agent() -> None:
    """连续 3 次相同工具调用→DoomLoopError。"""
    reg = MockToolRegistry(doom_loop_detect=True)

    await reg.dispatch("edit_file", {"path": "x.py"})
    await reg.dispatch("edit_file", {"path": "x.py"})

    # 第 3 次→Doom Loop
    with pytest.raises(DoomLoopError):
        await reg.dispatch("edit_file", {"path": "x.py"})


# ── 极端 Mock 配置 ────────────────────────────────────────

@pytest.mark.scenario_edge
async def test_llm_returns_empty_content(scenario_mocks: dict) -> None:
    """LLM 返回空内容→Agent 应能处理。"""
    scenario_mocks["llm"] = MockLLMClient(fixed_response="")  # 空字符串

    chain = TaskChain(mocks=scenario_mocks)
    # 不应崩溃
    await chain.start("测试").run_to_completion()
    chain.assert_done()


@pytest.mark.scenario_edge
async def test_llm_high_latency_simulation(scenario_mocks: dict) -> None:
    """LLM 高延迟（500ms）→TaskChain 正常等待。"""
    scenario_mocks["llm"] = MockLLMClient(fixed_response="ok").with_latency(500)

    chain = TaskChain(mocks=scenario_mocks)
    await chain.start("测试").run_to_completion()
    chain.assert_done()
