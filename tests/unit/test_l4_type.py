"""Step 4.1 L4 静态类型检查器单元测试。

覆盖：正向(类型正确) / 类型错误 / 空代码 / mypy 未安装 / mypy 超时。
全部 mock subprocess，不依赖真实 mypy。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.hallucination.l4_type import L4TypeValidator
from orbit.hallucination.schemas import HallucinationLevel


@pytest.fixture
def validator():
    """创建 L4 验证器，预先标记 mypy 可用（避免 which 检测）。"""
    v = L4TypeValidator(mypy_path="mypy")
    v._available = True
    return v


def _make_proc(returncode=0, stdout=b"", stderr=b""):
    """构造 mock asyncio subprocess 结果。"""
    proc = MagicMock()
    proc.returncode = returncode
    future = asyncio.Future()
    future.set_result((stdout, stderr))
    proc.communicate.return_value = future
    return proc


@pytest.mark.asyncio
async def test_l4_type_correct(validator):
    """正向：类型正确的代码 → passed=True。"""
    code = "def add(a: int, b: int) -> int:\n    return a + b"
    mock_proc = _make_proc(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await validator.validate(code)
    assert result.passed is True
    assert result.level == HallucinationLevel.L4_TYPE


@pytest.mark.asyncio
async def test_l4_type_error(validator):
    """AC3: 类型不匹配 → passed=False + 错误详情。"""
    code = "def add(a: str, b: str) -> int:\n    return a + b"
    mock_proc = _make_proc(
        returncode=1,
        stdout=b"tmp.py:1: error: Incompatible return value type (got str, expected int)\nFound 1 error in 1 file\n",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await validator.validate(code)
    assert result.passed is False
    assert result.level == HallucinationLevel.L4_TYPE
    assert any("Incompatible" in e for e in result.errors)


@pytest.mark.asyncio
async def test_l4_empty_code(validator):
    """边缘：空代码 → passed=True + warning。"""
    result = await validator.validate("")
    assert result.passed is True
    assert any("empty" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_l4_mypy_not_found():
    """边缘：mypy 未安装 → passed=False。"""
    v = L4TypeValidator(mypy_path="/nonexistent/mypy")
    v._available = False  # 模拟 which 检测失败
    result = await v.validate("x = 1")
    assert result.passed is False
    assert any("not installed" in e.lower() or "not found" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_l4_mypy_timeout(validator):
    """边缘：mypy 执行超时 → passed=False。"""
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await validator.validate("def f(): pass")
    assert result.passed is False
    assert any("timed out" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_l4_syntax_error_in_code(validator):
    """语法错误的代码 → mypy 返回非零 + 错误行。"""
    code = "def broken(:"
    mock_proc = _make_proc(
        returncode=1,
        stdout=b"tmp.py:1: error: invalid syntax\nFound 1 error in 1 file\n",
    )
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await validator.validate(code)
    assert result.passed is False
