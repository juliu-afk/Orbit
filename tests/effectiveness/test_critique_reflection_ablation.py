"""Phase 2: CritiqueAgent + ReflectionEngine 消融测试。

验证消融检查点正确生效——禁用后门禁/反思被跳过。
"""

from __future__ import annotations

import pytest

from orbit.effectiveness.ablation import AblationContext


class TestCritiqueGateAblation:
    """CritiqueAgent 消融。"""

    def test_critique_gate_disabled(self):
        AblationContext.reset()
        AblationContext.disable("critique_gate")
        assert AblationContext.is_disabled("critique_gate")
        AblationContext.reset()
        assert not AblationContext.is_disabled("critique_gate")

    def test_critique_gate_context_manager(self):
        AblationContext.reset()
        with AblationContext(["critique_gate"]):
            assert AblationContext.is_disabled("critique_gate")
        assert not AblationContext.is_disabled("critique_gate")


class TestReflectionEngineAblation:
    """ReflectionEngine 消融。"""

    def test_reflection_engine_disabled(self):
        AblationContext.reset()
        AblationContext.disable("reflection_engine")
        assert AblationContext.is_disabled("reflection_engine")
        AblationContext.reset()
        assert not AblationContext.is_disabled("reflection_engine")

    def test_reflection_engine_context_manager(self):
        AblationContext.reset()
        with AblationContext(["reflection_engine"]):
            assert AblationContext.is_disabled("reflection_engine")
        assert not AblationContext.is_disabled("reflection_engine")


class TestCombinedAblation:
    """组合消融。"""

    def test_disable_critique_and_reflection(self):
        AblationContext.reset()
        with AblationContext(["critique_gate", "reflection_engine"]):
            assert AblationContext.is_disabled("critique_gate")
            assert AblationContext.is_disabled("reflection_engine")
            assert not AblationContext.is_disabled("hallucination_L1")
        assert not AblationContext.is_disabled("critique_gate")
        assert not AblationContext.is_disabled("reflection_engine")
