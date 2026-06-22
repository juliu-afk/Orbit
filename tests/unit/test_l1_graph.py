"""Step 4.1 L1 图谱引用验证器单元测试。

覆盖：正向(符号存在) / 异常(不存在) / 空代码 / 语法错误 / 图谱查询失败。
全部 mock CodeGraphEngine，不依赖真实 DB。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.hallucination.l1_graph import L1GraphValidator
from orbit.hallucination.schemas import HallucinationLevel


@pytest.fixture
def mock_engine():
    """Mock CodeGraphEngine：exists() 返回由测试控制。"""
    engine = MagicMock()
    engine.exists = AsyncMock()
    return engine


@pytest.fixture
def validator(mock_engine):
    return L1GraphValidator(mock_engine)


@pytest.mark.asyncio
async def test_l1_all_symbols_exist(validator, mock_engine):
    """正向：代码中所有符号均在图谱中存在。"""
    mock_engine.exists.return_value = True
    code = "result = add(1, 2)\nprint(result)"
    result = await validator.validate(code)
    assert result.passed is True
    assert result.level == HallucinationLevel.L1_GRAPH
    # 验证确实查询了符号（add/print 是 builtin，跳过）
    assert mock_engine.exists.called


@pytest.mark.asyncio
async def test_l1_missing_symbol(validator, mock_engine):
    """AC1: 引用不存在的符号 → passed=False + GraphReferenceError 信息。"""
    # foo 存在，bar 不存在
    async def fake_exists(name):
        return name != "bar"

    mock_engine.exists.side_effect = fake_exists
    code = "x = foo()\ny = bar()"
    result = await validator.validate(code)
    assert result.passed is False
    assert result.level == HallucinationLevel.L1_GRAPH
    assert any("bar" in e for e in result.errors)
    assert "bar" in result.metadata.get("missing_symbols", [])


@pytest.mark.asyncio
async def test_l1_empty_code(validator, mock_engine):
    """边缘：空代码 → passed=True + warning。"""
    result = await validator.validate("")
    assert result.passed is True
    assert any("empty" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_l1_syntax_error(validator, mock_engine):
    """边缘：语法错误代码 → passed=False + 语法错误详情。"""
    code = "def broken(:"
    result = await validator.validate(code)
    assert result.passed is False
    assert any("Syntax" in e or "syntax" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_l1_graph_query_error(validator, mock_engine):
    """边缘：图谱查询异常 → passed=False + 错误信息。"""
    mock_engine.exists.side_effect = RuntimeError("DB connection lost")
    code = "x = some_func()"
    result = await validator.validate(code)
    assert result.passed is False
    assert any("Graph query" in e for e in result.errors)


@pytest.mark.asyncio
async def test_l1_builtins_skipped(validator, mock_engine):
    """内置函数（print/len 等）被跳过，不查询图谱。"""
    mock_engine.exists.return_value = True
    code = "print(len([1, 2, 3]))"
    result = await validator.validate(code)
    # print 和 len 都是 builtin，没有用户符号 → passed
    assert result.passed is True
    # 如果代码只有 builtins，不应该查询图谱
    assert not mock_engine.exists.called
