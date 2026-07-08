"""Phase 2: CritiqueAgent + ReflectionEngine 消融测试。

验证消融检查点是否在正确位置生效——禁用后门禁/反思被跳过。
"""

from __future__ import annotations

import pytest

from orbit.effectiveness.ablation import AblationContext


class TestCritiqueGateAblation:
    """CritiqueAgent 消融——禁用后门禁应被跳过。"""

    def test_critique_gate_disabled_via_ablation(self):
        """验证 critique_gate 消融目标可被禁用。"""
        AblationContext.reset()
        AblationContext.disable("critique_gate")
        assert AblationContext.is_disabled("critique_gate")
        AblationContext.reset()
        assert not AblationContext.is_disabled("critique_gate")

    def test_critique_gate_context_manager(self):
        """上下文管理器自动恢复。"""
        AblationContext.reset()
        with AblationContext(["critique_gate"]):
            assert AblationContext.is_disabled("critique_gate")
        assert not AblationContext.is_disabled("critique_gate")


class TestReflectionEngineAblation:
    """ReflectionEngine 消融——禁用后反思应被跳过。"""

    def test_reflection_engine_disabled_via_ablation(self):
        """验证 reflection_engine 消融目标可被禁用。"""
        AblationContext.reset()
        AblationContext.disable("reflection_engine")
        assert AblationContext.is_disabled("reflection_engine")
        AblationContext.reset()
        assert not AblationContext.is_disabled("reflection_engine")

    def test_reflection_engine_context_manager(self):
        """上下文管理器自动恢复。"""
        AblationContext.reset()
        with AblationContext(["reflection_engine"]):
            assert AblationContext.is_disabled("reflection_engine")
        assert not AblationContext.is_disabled("reflection_engine")


class TestCombinedAblation:
    """组合消融——同时禁多个模块。"""

    def test_disable_critique_and_reflection(self):
        """同时禁用两个门禁——验证互不干扰。"""
        AblationContext.reset()
        with AblationContext(["critique_gate", "reflection_engine"]):
            assert AblationContext.is_disabled("critique_gate")
            assert AblationContext.is_disabled("reflection_engine")
            # 未禁用项不受影响
            assert not AblationContext.is_disabled("hallucination_L1")
        # 全部恢复
        assert not AblationContext.is_disabled("critique_gate")
        assert not AblationContext.is_disabled("reflection_engine")
