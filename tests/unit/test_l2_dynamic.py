"""Step 4.1 L2 动态调用追踪器单元测试。

覆盖：正向(追踪正常+图谱验证) / 图谱缺失拦截 / 沙箱不可用 / 空代码 /
执行失败不阻断 / 代码注入验证。

全部 mock Sandbox + CodeGraphEngine，不依赖真实 Docker/DB。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.hallucination.l2_dynamic import L2DynamicTracer
from orbit.hallucination.schemas import HallucinationLevel


@pytest.fixture
def mock_sandbox():
    """Mock Sandbox。"""
    sandbox = MagicMock()
    sandbox.run = AsyncMock()
    sandbox.is_available = AsyncMock(return_value=True)
    return sandbox


@pytest.fixture
def mock_engine():
    """Mock CodeGraphEngine：exists() 返回 True（所有调用都在图谱中）。"""
    engine = MagicMock()
    engine.exists = AsyncMock(return_value=True)
    return engine


@pytest.fixture
def tracer(mock_sandbox, mock_engine):
    return L2DynamicTracer(mock_sandbox, mock_engine)


@pytest.mark.asyncio
async def test_l2_traces_and_verifies_calls(tracer, mock_sandbox, mock_engine):
    """正向：追踪到函数调用，全部在图谱中存在 → passed=True。"""
    mock_sandbox.run.return_value = 'some output\n__L2_TRACE_RESULT__["add", "compute"]\n'
    code = "def add(a, b): return a + b\nresult = add(1, 2)"
    result = await tracer.validate(code)
    assert result.passed is True
    assert result.level == HallucinationLevel.L2_DYNAMIC
    assert "add" in result.metadata["traced_calls"]
    assert "compute" in result.metadata["traced_calls"]
    assert result.metadata["call_count"] == 2
    # 验证确实查询了图谱
    assert mock_engine.exists.called


@pytest.mark.asyncio
async def test_l2_untracked_call_blocked(tracer, mock_sandbox, mock_engine):
    """审查 P2 修复：追踪到的调用不在图谱中 → passed=False。"""
    mock_sandbox.run.return_value = '__L2_TRACE_RESULT__["legit_func", "phantom_func"]\n'

    # phantom_func 不在图谱中
    async def fake_exists(name):
        return name != "phantom_func"

    mock_engine.exists.side_effect = fake_exists
    code = "result = getattr(obj, 'phantom_func')()"
    result = await tracer.validate(code)
    assert result.passed is False
    assert "phantom_func" in result.metadata["untracked_calls"]
    assert "Dynamic calls not found" in result.errors[0]


@pytest.mark.asyncio
async def test_l2_empty_code(tracer, mock_sandbox):
    """边缘：空代码 → passed=True + warning。"""
    result = await tracer.validate("")
    assert result.passed is True
    assert any("empty" in w.lower() for w in result.warnings)
    mock_sandbox.run.assert_not_called()


@pytest.mark.asyncio
async def test_l2_sandbox_unavailable(tracer, mock_sandbox):
    """边缘：沙箱不可用 → passed=True + warning。"""
    mock_sandbox.is_available.return_value = False
    code = "def f(): pass"
    result = await tracer.validate(code)
    assert result.passed is True
    assert any("unavailable" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_l2_execution_failure_not_blocking(tracer, mock_sandbox):
    """沙箱执行失败 → passed=True, L2 不阻断。"""
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


@pytest.mark.asyncio
async def test_l2_filters_internal_trace_funcs(tracer, mock_sandbox, mock_engine):
    """L2 自身注入的 _l2_trace 函数被过滤，不参与图谱验证。"""
    mock_sandbox.run.return_value = '__L2_TRACE_RESULT__["_l2_trace", "user_func"]\n'
    code = "def user_func(): pass\nuser_func()"
    result = await tracer.validate(code)
    assert result.passed is True
    # _l2_trace 被过滤
    assert "_l2_trace" not in result.metadata["traced_calls"]
    assert "user_func" in result.metadata["traced_calls"]
    # 不应查询 _l2_trace
    mock_engine.exists.assert_called_with("user_func")
