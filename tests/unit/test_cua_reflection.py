"""CUA Phase A 反思式 CoT 单元测试 (US2).

测试范围：L2ReflectionResult / L4BehaviorResult / L5ContractResult 模型 + 行为。
"""

from __future__ import annotations

import pytest

from orbit.hallucination.schemas import (
    HallucinationLevel,
    L2ReflectionResult,
    L4BehaviorResult,
    L5ContractResult,
    ValidationResult,
)


class TestL2ReflectionResult:
    """L2 反思式验证结果模型。"""

    def test_baseline_no_prediction_returns_plain_validation_result(self):
        """不传 predicted_calls 时，L2 应返回普通 ValidationResult（向后兼容）。"""
        result = ValidationResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            metadata={"traced_calls": ["foo", "bar"], "call_count": 2},
        )
        assert result.passed is True
        assert result.level == HallucinationLevel.L2_DYNAMIC
        assert not isinstance(result, L2ReflectionResult)

    def test_reflection_perfect_match_zero_deviation(self):
        """预测与实际完全匹配 → deviation_score=0.0。"""
        result = L2ReflectionResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            predicted_calls=["foo", "bar"],
            actual_calls=["foo", "bar"],
            deviation_score=0.0,
            unpredicted_calls=[],
            unexpected_calls=[],
        )
        assert result.deviation_score == 0.0
        assert result.unpredicted_calls == []
        assert result.unexpected_calls == []

    def test_reflection_full_mismatch_max_deviation(self):
        """预测与实际情况完全不同 → deviation_score=1.0。"""
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
        assert len(result.unpredicted_calls) == 2
        assert len(result.unexpected_calls) == 2

    def test_reflection_partial_match(self):
        """部分匹配 → 0 < deviation < 1。"""
        result = L2ReflectionResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            predicted_calls=["foo", "bar", "baz"],
            actual_calls=["foo", "qux"],
            deviation_score=0.67,
            unpredicted_calls=["bar", "baz"],
            unexpected_calls=["qux"],
        )
        assert 0.0 < result.deviation_score < 1.0
        assert "bar" in result.unpredicted_calls
        assert "qux" in result.unexpected_calls

    def test_reflection_empty_prediction(self):
        """空预测列表——Agent 预测不调用任何函数。"""
        result = L2ReflectionResult(
            passed=True,
            level=HallucinationLevel.L2_DYNAMIC,
            predicted_calls=[],
            actual_calls=["unexpected_func"],
            deviation_score=1.0,
            unpredicted_calls=[],
            unexpected_calls=["unexpected_func"],
        )
        assert result.predicted_calls == []
        assert len(result.unexpected_calls) == 1

    def test_reflection_deviation_bounded(self):
        """deviation_score 必须在 [0.0, 1.0] 区间内。"""
        with pytest.raises(Exception):  # Pydantic validation
            L2ReflectionResult(
                passed=True,
                level=HallucinationLevel.L2_DYNAMIC,
                predicted_calls=["foo"],
                actual_calls=[],
                deviation_score=1.5,  # 超出上限
            )


class TestL4BehaviorResult:
    """L4 行为反思验证结果模型。"""

    def test_baseline_no_behavior_prediction(self):
        """不传 predicted_behavior 时返回普通 ValidationResult。"""
        result = ValidationResult(
            passed=True,
            level=HallucinationLevel.L4_TYPE,
        )
        assert not isinstance(result, L4BehaviorResult)

    def test_behavior_match_when_mypy_passes(self):
        """mypy 通过 + 自述行为 → behavior_match=True。"""
        result = L4BehaviorResult(
            passed=True,
            level=HallucinationLevel.L4_TYPE,
            predicted_behavior="function returns str",
            actual_behavior="type check passed",
            behavior_match=True,
            behavior_diff="",
        )
        assert result.behavior_match is True
        assert result.behavior_diff == ""

    def test_behavior_mismatch_when_mypy_fails(self):
        """mypy 报类型错误 + 自述行为矛盾 → behavior_match=False。"""
        result = L4BehaviorResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["error: Incompatible return type"],
            predicted_behavior="function returns int",
            actual_behavior="type errors: Incompatible return type (got str, expected int)",
            behavior_match=False,
            behavior_diff="Predicted: function returns int\nActual: type errors: Incompatible return type...",
        )
        assert result.behavior_match is False
        assert result.behavior_diff != ""

    def test_mypy_unavailable_behavior(self):
        """mypy 不可用 → behavior_match=False + 原因。"""
        result = L4BehaviorResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=["mypy is not installed or not found in PATH"],
            predicted_behavior="function returns int",
            actual_behavior="mypy unavailable",
            behavior_match=False,
            behavior_diff="mypy not available—cannot verify behavior",
        )
        assert result.behavior_match is False


class TestL5ContractResult:
    """L5 契约反思验证结果模型。"""

    def test_baseline_no_self_claimed(self):
        """不传 self_claimed_contract 时返回普通 L5ValidationResult。"""
        from orbit.hallucination.schemas import L5ValidationResult

        result = L5ValidationResult(
            passed=True,
            level=HallucinationLevel.L5_Z3,
            z3_status="unsat",
        )
        assert not isinstance(result, L5ContractResult)
        assert result.z3_status == "unsat"

    def test_contract_match_when_consistent(self):
        """自述契约与 Z3 契约一致 → contract_mismatch=False。"""
        result = L5ContractResult(
            passed=True,
            level=HallucinationLevel.L5_Z3,
            z3_status="unsat",
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="ensures: result > 0",
            contract_mismatch=False,
        )
        assert result.contract_mismatch is False
        assert result.z3_status == "unsat"

    def test_contract_mismatch_detected(self):
        """自述契约与 Z3 契约矛盾 → contract_mismatch=True，但不影响 passed。"""
        result = L5ContractResult(
            passed=True,  # Z3 验证通过（unsat），但契约描述不一致
            level=HallucinationLevel.L5_Z3,
            z3_status="unsat",
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="ensures: result == x + y",
            contract_mismatch=True,
        )
        assert result.contract_mismatch is True
        # 关键：即使契约描述矛盾，Z3 判定仍独立
        assert result.passed is True
        assert result.z3_status == "unsat"

    def test_no_formal_decorator_with_reflection(self):
        """无 @formal 装饰器但有自述契约 → 跳过，contract_mismatch=False。"""
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
        assert result.contract_mismatch is False

    def test_z3_counterexample_with_contract_mismatch(self):
        """Z3 找到反例 + 契约矛盾 → 两个信号独立记录。"""
        result = L5ContractResult(
            passed=False,
            level=HallucinationLevel.L5_Z3,
            z3_status="sat",
            errors=["Counterexample found: {'x': 0, 'y': -1}"],
            counterexample={"x": "0", "y": "-1"},
            self_claimed_contract="ensures: result > 0",
            z3_verified_contract="ensures: result == x + y",
            contract_mismatch=True,
        )
        assert result.passed is False
        assert result.z3_status == "sat"
        assert result.counterexample is not None
        assert result.contract_mismatch is True


class TestBackwardCompatibility:
    """向后兼容——所有新参数默认 None 时行为不变。"""

    def test_validation_result_no_reflection_fields(self):
        """ValidationResult 不应包含反思字段。"""
        result = ValidationResult(passed=True, level=HallucinationLevel.L2_DYNAMIC)
        assert not hasattr(result, "predicted_calls")
        assert not hasattr(result, "deviation_score")

    def test_l5_validation_result_no_reflection_fields(self):
        """L5ValidationResult 不应包含契约反思字段。"""
        from orbit.hallucination.schemas import L5ValidationResult

        result = L5ValidationResult(
            passed=True, level=HallucinationLevel.L5_Z3, z3_status="unsat"
        )
        assert not hasattr(result, "self_claimed_contract")
        assert not hasattr(result, "contract_mismatch")

    def test_l2_reflection_inherits_validation_result(self):
        """L2ReflectionResult 是 ValidationResult 的子类——polymorphic safe。"""
        result = L2ReflectionResult(
            passed=True, level=HallucinationLevel.L2_DYNAMIC
        )
        assert isinstance(result, ValidationResult)
        assert result.passed is True

    def test_l5_contract_inherits_l5_validation(self):
        """L5ContractResult 是 L5ValidationResult 的子类——polymorphic safe。"""
        from orbit.hallucination.schemas import L5ValidationResult

        result = L5ContractResult(
            passed=True, level=HallucinationLevel.L5_Z3, z3_status="unsat"
        )
        assert isinstance(result, L5ValidationResult)
