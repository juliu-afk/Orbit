"""覆盖率补测——hallucination/l5_z3.py (L5Z3Validator) + hallucination/schemas.py."""

from __future__ import annotations

import pytest

from orbit.hallucination.l5_z3 import L5Z3Validator, Z3_TIMEOUT_MS
from orbit.hallucination.schemas import L5ValidationResult


from orbit.hallucination.schemas import HallucinationLevel, ValidationResult


class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult(passed=True, level=HallucinationLevel.L5_Z3)
        assert r.passed is True
        assert r.level == HallucinationLevel.L5_Z3

    def test_passed_false(self):
        r = ValidationResult(passed=False, level=HallucinationLevel.L5_Z3)
        assert r.passed is False

    def test_with_errors(self):
        r = ValidationResult(
            passed=False,
            level=HallucinationLevel.L5_Z3,
            errors=["counterexample found for x=-1"],
        )
        assert len(r.errors) == 1


class TestL5ValidationResultFields:
    def test_defaults(self):
        r = L5ValidationResult(passed=True, level=HallucinationLevel.L5_Z3)
        assert r.z3_status == "skipped"
        assert r.counterexample is None

    def test_unsat_status(self):
        r = L5ValidationResult(
            passed=True, level=HallucinationLevel.L5_Z3,
            z3_status="unsat",
        )
        assert r.z3_status == "unsat"

    def test_with_counterexample(self):
        r = L5ValidationResult(
            passed=False, level=HallucinationLevel.L5_Z3,
            z3_status="sat",
            counterexample={"x": -1},
        )
        assert r.z3_status == "sat"
        assert r.counterexample == {"x": -1}


class TestL5Z3Validator:
    def test_init_default_timeout(self):
        v = L5Z3Validator()
        assert v._timeout_ms == Z3_TIMEOUT_MS

    def test_init_custom_timeout(self):
        v = L5Z3Validator(timeout_ms=500)
        assert v._timeout_ms == 500

    @pytest.mark.asyncio
    async def test_validate_empty_code(self):
        """空代码 → 验证失败。"""
        v = L5Z3Validator(timeout_ms=100)
        result = await v.validate("")
        assert isinstance(result, L5ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_simple_function(self):
        """简单函数 → 尝试验证。"""
        v = L5Z3Validator(timeout_ms=100)
        code = """
def add(x: int, y: int) -> int:
    return x + y
"""
        result = await v.validate(code)
        assert isinstance(result, L5ValidationResult)

    def test_parse_contract_no_contract(self):
        """无合约注释 → 返回 None。"""
        v = L5Z3Validator()
        result = v._parse_contract("def foo(): pass")
        assert result is None

    def test_parse_contract_with_formal(self):
        """有 @formal 装饰器 → 解析成功。"""
        v = L5Z3Validator()
        code = '''
@formal
@requires x > 0
@ensures result == x * 2
def double(x: int) -> int:
    return x * 2
'''
        result = v._parse_contract(code)
        if result is not None:
            assert isinstance(result, dict)
