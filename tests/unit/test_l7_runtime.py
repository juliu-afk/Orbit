"""L7 沙箱运行时验证器测试。mock Sandbox。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.hallucination.l7_runtime import L7RuntimeValidator
from orbit.sandbox.executor import SandboxExecutionError


@pytest.fixture
def mock_sandbox():
    s = MagicMock()
    s.run = AsyncMock()
    s.is_available = AsyncMock(return_value=True)
    return s


@pytest.fixture
def validator(mock_sandbox):
    return L7RuntimeValidator(mock_sandbox)


@pytest.mark.asyncio
async def test_l7_assertions_pass(validator, mock_sandbox):
    """AC4: assert 全部通过 → passed=True。"""
    mock_sandbox.run.return_value = ""
    code = "def add(a, b): return a + b"
    result = await validator.validate(code, ["add(1,2) == 3"])
    assert result.passed is True
    assert result.metadata["all_passed"] is True


@pytest.mark.asyncio
async def test_l7_assertion_fails(validator, mock_sandbox):
    """AC4: assert 失败 → SandboxExecutionError → passed=False。"""
    mock_sandbox.run.side_effect = SandboxExecutionError("assert 1 == 2 failed")
    code = "def add(a, b): return a + b"
    result = await validator.validate(code, ["add(1,2) == 4"])
    assert result.passed is False
    assert "Runtime assertion failed" in result.errors[0]


@pytest.mark.asyncio
async def test_l7_empty_code(validator, mock_sandbox):
    """空代码 → skipped。"""
    result = await validator.validate("")
    assert result.passed is True
    assert any("empty" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_l7_sandbox_unavailable(validator, mock_sandbox):
    """沙箱不可用 → fail-closed (P0-7: 无法验证=不应信任)。"""
    mock_sandbox.is_available.return_value = False
    result = await validator.validate("x = 1")
    assert result.passed is False
    assert any("sandbox" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_l7_no_assertions(validator, mock_sandbox):
    """无 assert → 仅执行代码确认无误。"""
    mock_sandbox.run.return_value = ""
    code = "x = 1 + 1"
    result = await validator.validate(code)
    assert result.passed is True
