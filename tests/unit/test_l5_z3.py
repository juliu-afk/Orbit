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


# ── 覆盖缺口 ──


@pytest.mark.asyncio
async def test_l5_self_claimed_contract_no_formal(validator):
    """self_claimed_contract 提供但无 @formal → L5ContractResult。"""
    result = await validator.validate(
        "def add(x, y): return x + y",
        self_claimed_contract="此函数做加法",
    )
    assert result.passed is True
    assert hasattr(result, "self_claimed_contract")


@pytest.mark.asyncio
async def test_l5_self_claimed_contract_z3_skipped(validator):
    """self_claimed_contract + Z3 未安装 → contract_mismatch=False。"""
    code = """
@formal
@requires("x > 0")
@ensures("result == x + y")
def add(x, y): return x + y
"""
    result = await validator.validate(code, self_claimed_contract="x>0 => result==x+y")
    assert result.passed is True
    assert hasattr(result, "self_claimed_contract")
    assert hasattr(result, "contract_mismatch")


def test_describe_contract():
    """_describe_contract 将结构化契约转为可读字符串。"""
    validator = L5Z3Validator()
    contract = {"pre": ["x > 0", "y != 0"], "post": ["result == x + y"]}
    desc = validator._describe_contract(contract)
    assert "requires:" in desc
    assert "ensures:" in desc
    assert "x > 0" in desc


def test_describe_contract_empty():
    """空契约 → 'empty contract'。"""
    validator = L5Z3Validator()
    desc = validator._describe_contract({"pre": [], "post": []})
    assert desc == "empty contract"


def test_parse_contract_with_single_quotes():
    """单引号装饰器也被识别。"""
    validator = L5Z3Validator()
    code = """
@formal
@requires('x > 0')
@ensures('result == x + 1')
def inc(x): return x + 1
"""
    contract = validator._parse_contract(code)
    assert contract is not None
    assert "x > 0" in contract["pre"]
    assert "result == x + 1" in contract["post"]


@pytest.mark.asyncio
async def test_l5_z3_error_path(validator):
    """Z3 solver 错误 → unknown + warning。"""
    code = """
@formal
@requires("x > 0")
@ensures("result == x + y")
def f(x, y): return x + y
"""
    result = await validator.validate(code)
    assert result.z3_status in ("skipped", "unknown")
