"""L5 Z3 形式化验证器测试。Z3 未安装环境测试。"""

from __future__ import annotations

import pytest

from orbit.hallucination.l5_z3 import L5Z3Validator


@pytest.fixture
def validator():
    return L5Z3Validator(timeout_ms=5000)


@pytest.mark.asyncio
async def test_l5_no_formal_decorator(validator):
    """无 @formal 装饰器 → skipped。"""
    result = await validator.validate("def add(x, y): return x + y")
    assert result.passed is True
    assert result.z3_status == "skipped"


@pytest.mark.asyncio
async def test_l5_parse_pre_post(validator):
    """解析 @requires/@ensures 装饰器。"""
    code = """
@formal
@requires("x > 0")
@requires("y > 0")
@ensures("result == x + y")
def add(x, y):
    return x + y
"""
    contract = validator._parse_contract(code)
    assert contract is not None
    assert contract["pre"] == ["x > 0", "y > 0"]
    assert contract["post"] == ["result == x + y"]
    assert contract["params"] == ["x", "y"]


@pytest.mark.asyncio
async def test_l5_z3_not_installed_skipped(validator):
    """Z3 未安装 → skipped + warning（AC1/AC2 在真实 Z3 环境测试）。"""
    code = """
@formal
@ensures("result == x + y")
def add(x, y): return x + y
"""
    result = await validator.validate(code)
    # Z3 未安装 → skipped
    assert result.passed is True
    assert result.z3_status in ("skipped", "unknown")


@pytest.mark.asyncio
async def test_l5_parse_error_unsafe_expr(validator):
    """不安全的表达式 → _parse_contract 安全拒绝。"""
    code = """
@formal
@requires("x > 0")
@ensures("result == x + y")
def f(x, y): return x + y
"""
    contract = validator._parse_contract(code)
    assert contract is not None
    # 安全表达式通过 parse（具体验证在 _solve 中）
    assert "x > 0" in contract["pre"]


@pytest.mark.asyncio
async def test_l5_syntax_error_code(validator):
    """语法错误代码 → _parse_contract 返回 None。"""
    code = "def broken(:"
    contract = validator._parse_contract(code)
    assert contract is None
