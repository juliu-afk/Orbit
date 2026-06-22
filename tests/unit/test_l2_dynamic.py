"""Step 4.1 L2 动态调用追踪器单元测试。

覆盖：正向(追踪正常) / 沙箱不可用 / 空代码 / 执行失败不阻断。
全部 mock Sandbox，不依赖真实 Docker。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.hallucination.l2_dynamic import L2DynamicTracer
from orbit.hallucination.schemas import HallucinationLevel


@pytest.fixture
def mock_sandbox():
    """Mock Sandbox：run() 和 is_available() 由测试控制。"""
    sandbox = MagicMock()
    sandbox.run = AsyncMock()
    sandbox.is_available = AsyncMock(return_value=True)
    return sandbox


@pytest.fixture
def tracer(mock_sandbox):
    return L2DynamicTracer(mock_sandbox)


@pytest.mark.asyncio
async def test_l2_traces_function_calls(tracer, mock_sandbox):
    """正向：沙箱执行追踪包装代码，返回 traced_calls。"""
    mock_sandbox.run.return_value = (
        "some user output\n__L2_TRACE_RESULT__[\"add\", \"compute\"]\n"
    )
    code = "def add(a, b): return a + b\nresult = add(1, 2)"
    result = await tracer.validate(code)
    assert result.passed is True
    assert result.level == HallucinationLevel.L2_DYNAMIC
    assert "add" in result.metadata["traced_calls"]
    assert "compute" in result.metadata["traced_calls"]
    assert result.metadata["call_count"] == 2


@pytest.mark.asyncio
async def test_l2_empty_code(tracer, mock_sandbox):
    """边缘：空代码 → passed=True + warning。"""
    result = await tracer.validate("")
    assert result.passed is True
    assert any("empty" in w.lower() for w in result.warnings)
    mock_sandbox.run.assert_not_called()


@pytest.mark.asyncio
async def test_l2_sandbox_unavailable(tracer, mock_sandbox):
    """边缘：沙箱不可用 → passed=True + warning（L2 不阻断）。"""
    mock_sandbox.is_available.return_value = False
    code = "def f(): pass"
    result = await tracer.validate(code)
    assert result.passed is True
    assert any("unavailable" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_l2_execution_failure_not_blocking(tracer, mock_sandbox):
    """沙箱执行失败（如代码运行时异常）→ L2 不阻断。"""
    mock_sandbox.run.side_effect = RuntimeError("Sandbox crashed")
    code = "raise RuntimeError('boom')"
    result = await tracer.validate(code)
    assert result.passed is True
    assert any("execution" in w.lower() for w in result.warnings)
    assert "execution_error" in result.metadata


@pytest.mark.asyncio
async def test_l2_no_trace_result_in_output(tracer, mock_sandbox):
    """沙箱输出无追踪标记 → traced_calls 为空列表。"""
    mock_sandbox.run.return_value = "just regular output, no trace marker"
    code = "print('hello')"
    result = await tracer.validate(code)
    assert result.passed is True
    assert result.metadata["traced_calls"] == []


@pytest.mark.asyncio
async def test_l2_trace_code_injected(tracer, mock_sandbox):
    """AC4: 验证 sys.settrace 包装代码被注入。"""
    mock_sandbox.run.return_value = "some output\n__L2_TRACE_RESULT__[]"
    code = "x = getattr(obj, 'method')()"
    await tracer.validate(code)
    called_code = mock_sandbox.run.call_args[0][0]
    assert "sys.settrace" in called_code
    assert "_l2_trace" in called_code
    assert "getattr(obj, 'method')()" in called_code
    assert "__L2_TRACE_RESULT__" in called_code
