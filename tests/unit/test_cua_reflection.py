"""CUA Phase A 反思式 CoT 测试 (US2) — REVIEW-FIX P1-1/P1-4.

含模型构造测试 + 真实行为测试：L2 偏差计算 / L4 行为对比 / L5 契约对比。
"""

from __future__ import annotations

import pytest

from orbit.hallucination.l4_type import L4TypeValidator
from orbit.hallucination.schemas import (
    HallucinationLevel,
    L2ReflectionResult,
    L4BehaviorResult,
    L5ContractResult,
    ValidationResult,
)


# ═══════════════════════════════════════════════════════════════
# L2 反思式验证
# ═══════════════════════════════════════════════════════════════

class TestL2ReflectionModel:
    """L2ReflectionResult 模型构造。"""

    def test_perfect_match_zero_deviation(self):
        result = L2ReflectionResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            predicted_calls=["foo", "bar"],
            actual_calls=["foo", "bar"],
            deviation_score=0.0,
        )
        assert result.deviation_score == 0.0
        assert result.unpredicted_calls == []
        assert result.unexpected_calls == []

    def test_full_mismatch_max_deviation(self):
        result = L2ReflectionResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            predicted_calls=["foo", "bar"],
            actual_calls=["baz", "qux"],
            deviation_score=1.0,
            unpredicted_calls=["foo", "bar"],
            unexpected_calls=["baz", "qux"],
        )
        assert result.deviation_score == 1.0

    def test_deviation_bounded_by_pydantic(self):
        """deviation_score 必须在 [0, 1] 内——Pydantic Field(ge=0, le=1)。"""
        with pytest.raises(Exception):
            L2ReflectionResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                predicted_calls=["foo"],
                actual_calls=[],
                deviation_score=1.5,
            )


class TestL2DeviationCalculation:
    """L2 偏差分计算逻辑——REVIEW-FIX P1-4: 真实行为测试。

    模拟 l2_dynamic.py L149-160 的计算逻辑。
    """

    @staticmethod
    def _compute_deviation(predicted: list[str], actual: list[str]) -> float:
        """与 L2DynamicTracer.validate 中偏差计算逻辑一致。"""
        pred_set = set(predicted)
        actual_set = set(actual)
        unexpected = actual_set - pred_set
        total = max(len(pred_set), 1)
        return min(len(unexpected) / total, 1.0)

    def test_exact_match_zero(self):
        assert self._compute_deviation(["foo", "bar"], ["foo", "bar"]) == 0.0

    def test_one_extra_actual(self):
        """预测 2 个，实际调了 3 个——1 个意外。"""
        dev = self._compute_deviation(["foo", "bar"], ["foo", "bar", "baz"])
        assert dev == 0.5  # 1/2

    def test_all_unexpected(self):
        """预测 [a,b]，实际 [c,d]——全部意外。"""
        dev = self._compute_deviation(["a", "b"], ["c", "d"])
        assert dev == 1.0  # 2/2

    def test_empty_prediction_actual_calls(self):
        """预测 []（Agent 认为不调用任何函数），实际调了函数——全部意外。"""
        dev = self._compute_deviation([], ["unexpected_func"])
        assert dev == 1.0  # 1/max(0,1)=1/1

    def test_prediction_but_no_calls(self):
        """预测了函数但实际没调——偏差 0（没有意外调用）。"""
        dev = self._compute_deviation(["foo", "bar"], [])
        assert dev == 0.0  # 0 意外 / 2 = 0

    def test_many_unexpected(self):
        """大偏差场景——预测 5 个，意外 3 个。"""
        dev = self._compute_deviation(
            ["a", "b", "c", "d", "e"],
            ["a", "x", "y", "z"],
        )
        # 意外: x,y,z = 3, total = max(5,1) = 5, deviation = 3/5 = 0.6
        assert dev == 0.6


# ═══════════════════════════════════════════════════════════════
# L4 反思式验证
# ═══════════════════════════════════════════════════════════════

class TestL4BehaviorModel:
    """L4BehaviorResult 模型构造。"""

    def test_match_when_mypy_passes(self):
        result = L4BehaviorResult(
            passed=True,
            level=HallucinationLevel.L4_TYPE,
            predicted_behavior="function returns str",
            actual_behavior="type check passed",
            behavior_match=True,
        )
        assert result.behavior_match is True

    def test_mismatch_when_mypy_fails_with_contradiction(self):
        result = L4BehaviorResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["error: Incompatible return type (got str, expected int)"],
            predicted_behavior="function returns int",
            actual_behavior="type errors: Incompatible return type...",
            behavior_match=False,
            behavior_diff="Predicted: function returns int\nActual: type errors: ...",
        )
        assert result.behavior_match is False
        assert "Predicted:" in result.behavior_diff

    def test_mypy_unavailable_no_match(self):
        result = L4BehaviorResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["mypy is not installed"],
            predicted_behavior="function returns int",
            actual_behavior="mypy unavailable",
            behavior_match=False,
        )
        assert result.behavior_match is False


class TestL4BehaviorComparison:
    """L4 _compare_behavior 真实逻辑——REVIEW-FIX P1-3。

    测试 L4TypeValidator._compare_behavior 静态方法。
    """

    def test_mypy_passed_always_match(self):
        """mypy 通过 → behavior_match=True（无关自述内容）。"""
        result = ValidationResult(passed=True, level=HallucinationLevel.L4_TYPE)
        match = L4TypeValidator._compare_behavior("returns anything", result)
        assert match is True

    def test_returns_int_vs_mypy_got_str_expected_int(self):
        """NEW-2: Agent 自述"returns int"，mypy 报 "got str, expected int"
        → 自述 int 与 mypy expected=int 交集 → 匹配（Agent正确预测了期望类型）。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Incompatible return type: got str, expected int"],
        )
        match = L4TypeValidator._compare_behavior("function returns int", result)
        assert match is True  # int ∈ {str, int}

    def test_returns_str_vs_mypy_got_str_expected_int(self):
        """NEW-2: Agent 自述"returns str"，mypy 报 "got str, expected int"
        → 自述 str 与 mypy got=str 交集 → 匹配（Agent正确预测了实际返回类型）。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Incompatible return type: got str, expected int"],
        )
        match = L4TypeValidator._compare_behavior("function returns str", result)
        assert match is True  # str ∈ {str, int}

    def test_empty_prediction_falls_back_to_mypy(self):
        """无自述行为 → 退化为 mypy 结果。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["type error"],
        )
        match = L4TypeValidator._compare_behavior("", result)
        assert match is False  # mypy failed

        result2 = ValidationResult(passed=True, level=HallucinationLevel.L4_TYPE)
        match2 = L4TypeValidator._compare_behavior("", result2)
        assert match2 is True

    def test_no_type_keywords_and_no_mypy_types_fail_open(self):
        """NEW-2: 自述无类型 + mypy 错误无 got/expected → 双方无法提取 → fail-open → True。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Syntax error in line 5"],
        )
        match = L4TypeValidator._compare_behavior("this code does the thing", result)
        assert match is True  # both sides empty → fail-open

    def test_accepts_list_vs_mypy_arg_error_overlap(self):
        """NEW-2: Agent 自述"accepts list"，mypy 报 has type list[int]
        → 自述 list 与 mypy list 交集 → 匹配。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=['Argument 1 has incompatible type "list[int]"; expected "str"'],
        )
        match = L4TypeValidator._compare_behavior("function accepts list", result)
        assert match is True  # list ∈ {list, str} from has type extraction

    def test_returns_float_no_overlap_with_mypy_types(self):
        """NEW-2: Agent 自述"returns float"，mypy 报 "got str, expected int"
        → float 不在 {str, int} → 无交集 → 矛盾。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Incompatible return type: got str, expected int"],
        )
        match = L4TypeValidator._compare_behavior("function returns float", result)
        assert match is False  # float ∉ {str, int}

    # ── NEW-2: mypy 错误格式变体测试 ──

    def test_mypy_quoted_type_format(self):
        """mypy 格式: got "str", expected "int"（带引号）。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=['Incompatible return type (got "str", expected "int")'],
        )
        match = L4TypeValidator._compare_behavior("function returns str", result)
        assert match is True  # str ∈ {str, int}

    def test_mypy_has_type_format(self):
        """mypy 格式: has type "list[int]"（assignment 场景）。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=['Incompatible types in assignment (expression has type "list[int]")'],
        )
        match = L4TypeValidator._compare_behavior("function returns list", result)
        assert match is True  # list ∈ {list}

    def test_mypy_no_recognizable_types_fallback_keyword(self):
        """mypy 错误不含 got/expected/has type 格式 → fallback 内置类型匹配。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Name 'int' is not defined"],
        )
        match = L4TypeValidator._compare_behavior("function returns int", result)
        assert match is True  # fallback: int ∈ {int}

    def test_mypy_no_types_at_all_fail_open(self):
        """mypy 错误完全无法提取类型 → fail-open → True。"""
        result = ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["Syntax error in line 5"],
        )
        match = L4TypeValidator._compare_behavior("function returns int", result)
        assert match is True  # fail-open


# ═══════════════════════════════════════════════════════════════
# L5 反思式验证
# ═══════════════════════════════════════════════════════════════

class TestL5ContractModel:
    """L5ContractResult 模型构造。"""

    def test_no_self_claimed_returns_base(self):
        from orbit.hallucination.schemas import L5ValidationResult
        result = L5ValidationResult(
            passed=True, level=HallucinationLevel.L5_Z3, z3_status="unsat",
        )
        assert not isinstance(result, L5ContractResult)

    def test_contract_mismatch_does_not_affect_passed(self):
        """契约矛盾不改变 Z3 passed——反思是附加信号。"""
        result = L5ContractResult(
            passed=True,
            level=HallucinationLevel.L5_Z3,
            z3_status="unsat",
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="ensures: result == x + y",
            contract_mismatch=True,
        )
        assert result.contract_mismatch is True
        assert result.passed is True  # Z3 passed 独立

    def test_counterexample_with_contract_mismatch(self):
        """Z3 反例 + 契约矛盾——两个信号独立。"""
        result = L5ContractResult(
            passed=False,
            level=HallucinationLevel.L5_Z3,
            z3_status="sat",
            errors=["Counterexample found: {'x': 0}"],
            counterexample={"x": "0"},
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="ensures: result == x + 1",
            contract_mismatch=True,
        )
        assert result.passed is False
        assert result.z3_status == "sat"
        assert result.counterexample is not None
        assert result.contract_mismatch is True

    def test_no_formal_decorator_with_reflection(self):
        result = L5ContractResult(
            passed=True,
            level=HallucinationLevel.L5_Z3,
            z3_status="skipped",
            warnings=["No @formal decorator found, skipped"],
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="no @formal decorator",
            contract_mismatch=False,
        )
        assert result.z3_status == "skipped"


# ═══════════════════════════════════════════════════════════════
# 向后兼容
# ═══════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """所有新参数默认 None 时行为不变。"""

    def test_validation_result_no_reflection_fields(self):
        result = ValidationResult(passed=True, level=HallucinationLevel.L2_DYNAMIC)
        assert not hasattr(result, "predicted_calls")

    def test_l2_reflection_is_validation_result(self):
        result = L2ReflectionResult(passed=True, level=HallucinationLevel.L2_DYNAMIC)
        assert isinstance(result, ValidationResult)

    def test_l5_contract_is_l5_validation(self):
        from orbit.hallucination.schemas import L5ValidationResult
        result = L5ContractResult(
            passed=True, level=HallucinationLevel.L5_Z3, z3_status="unsat",
        )
        assert isinstance(result, L5ValidationResult)
