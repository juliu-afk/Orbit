"""消融 harness 单元测试——验证 AblationContext 正确性。"""
from __future__ import annotations

import pytest

from orbit.effectiveness.ablation import ABLATION_TARGETS, AblationContext


class TestAblationContext:
    """AblationContext 基本操作。"""

    def setup_method(self):
        """每个测试前重置状态。"""
        AblationContext.reset()

    def test_disable_single_target(self):
        AblationContext.disable("hallucination_L1")
        assert AblationContext.is_disabled("hallucination_L1")

    def test_disable_multiple_targets(self):
        AblationContext.disable("hallucination_L1", "hallucination_L3", "critique_gate")
        assert AblationContext.is_disabled("hallucination_L1")
        assert AblationContext.is_disabled("hallucination_L3")
        assert AblationContext.is_disabled("critique_gate")

    def test_is_disabled_unknown_target_returns_false(self):
        """未定义的 target 静默忽略——不崩。"""
        AblationContext.disable("nonexistent_target")
        assert not AblationContext.is_disabled("nonexistent_target")

    def test_enable_restores(self):
        AblationContext.disable("hallucination_L3")
        assert AblationContext.is_disabled("hallucination_L3")
        AblationContext.enable("hallucination_L3")
        assert not AblationContext.is_disabled("hallucination_L3")

    def test_reset_clears_all(self):
        AblationContext.disable("hallucination_L1", "critique_gate", "reflection_engine")
        AblationContext.reset()
        assert AblationContext.active_targets() == set()

    def test_active_targets_returns_copy(self):
        AblationContext.disable("hallucination_L1")
        targets = AblationContext.active_targets()
        assert targets == {"hallucination_L1"}
        # 副本不应影响原状态
        targets.add("hallucination_L3")
        assert "hallucination_L3" not in AblationContext.active_targets()

    def test_is_disabled_returns_false_when_nothing_disabled(self):
        assert not AblationContext.is_disabled("hallucination_L1")
        assert not AblationContext.is_disabled("critique_gate")


class TestAblationContextManager:
    """AblationContext 上下文管理器。"""

    def setup_method(self):
        AblationContext.reset()

    def test_context_manager_disables_and_restores(self):
        assert not AblationContext.is_disabled("hallucination_L3")
        with AblationContext(["hallucination_L3"]):
            assert AblationContext.is_disabled("hallucination_L3")
        # 退出后恢复
        assert not AblationContext.is_disabled("hallucination_L3")

    def test_context_manager_multiple_targets(self):
        with AblationContext(["hallucination_L1", "reflection_engine", "critique_gate"]):
            assert AblationContext.is_disabled("hallucination_L1")
            assert AblationContext.is_disabled("reflection_engine")
            assert AblationContext.is_disabled("critique_gate")
            # 未禁用项不受影响
            assert not AblationContext.is_disabled("hallucination_L5")
        # 全部恢复
        assert not AblationContext.is_disabled("hallucination_L1")
        assert not AblationContext.is_disabled("reflection_engine")

    def test_nested_context_managers(self):
        """嵌套消融——退出内层只恢复内层禁用的。"""
        with AblationContext(["hallucination_L1"]):
            assert AblationContext.is_disabled("hallucination_L1")
            with AblationContext(["hallucination_L3"]):
                assert AblationContext.is_disabled("hallucination_L1")
                assert AblationContext.is_disabled("hallucination_L3")
            # 退出内层——L3 恢复，L1 仍禁用
            assert AblationContext.is_disabled("hallucination_L1")
            assert not AblationContext.is_disabled("hallucination_L3")
        # 退出外层——全部恢复
        assert not AblationContext.is_disabled("hallucination_L1")

    def test_exception_in_context_still_restores(self):
        """上下文内异常不应阻塞恢复。"""
        try:
            with AblationContext(["hallucination_L3"]):
                assert AblationContext.is_disabled("hallucination_L3")
                raise ValueError("模拟异常")
        except ValueError:
            pass
        # 恢复不受异常影响
        assert not AblationContext.is_disabled("hallucination_L3")


class TestAblationTargetsRegistry:
    """ABLATION_TARGETS 注册表完整性。"""

    def test_registry_has_expected_keys(self):
        """核心可消融目标应全部注册。"""
        expected = {
            "hallucination_L1", "hallucination_L2", "hallucination_L3",
            "hallucination_L4", "hallucination_L5", "hallucination_L6",
            "hallucination_L7", "hallucination_L8",
            "reflection_engine", "goal_judge", "preact_guard", "vigil_healer",
            "critique_gate", "regression_guard",
            "context_stage2", "context_stage3",
        }
        assert expected.issubset(set(ABLATION_TARGETS.keys()))

    def test_targets_have_descriptions(self):
        """每个消融目标应有人读描述。"""
        for key, desc in ABLATION_TARGETS.items():
            assert desc, f"Target '{key}' has empty description"
            assert len(desc) >= 5, f"Target '{key}' description too short"
