"""测试 ModeIndicator——模式前缀标签生成."""

from __future__ import annotations

from orbit.modes.indicator import ModeIndicator


# ════════════════════════════════════════════
# Agent 模式前缀
# ════════════════════════════════════════════


def test_clarify_depth_first() -> None:
    """clarify + 深度优先 → [🔍 clarify·深度模式]."""
    label = ModeIndicator.for_agent("clarify", "depth_first")
    assert "🔍" in label
    assert "clarify" in label
    assert "深度模式" in label


def test_clarify_breadth_first() -> None:
    """clarify + 广度优先 → [🔍 clarify·广角模式]."""
    label = ModeIndicator.for_agent("clarify", "breadth_first")
    assert "广角模式" in label


def test_mode_none_default() -> None:
    """mode=None → [🔍 clarify·默认]."""
    label = ModeIndicator.for_agent(None, "depth_first")
    assert "默认" in label


def test_fast_preset_detected() -> None:
    """max_questions=8 → 快速模式."""
    label = ModeIndicator.for_agent("clarify", "breadth_first", max_questions=8)
    assert "快速模式" in label


def test_deep_preset_detected() -> None:
    """max_questions=30 → 深入模式."""
    label = ModeIndicator.for_agent("clarify", "depth_first", max_questions=30)
    assert "深入模式" in label


# ════════════════════════════════════════════
# Compose 技能前缀
# ════════════════════════════════════════════


def test_compose_plan_prefix() -> None:
    """compose:plan → [📋 compose:plan]."""
    label = ModeIndicator.for_compose_skill("compose:plan")
    assert "📋" in label
    assert "compose:plan" in label


def test_compose_review_prefix() -> None:
    """compose:review → [🔎 compose:review]."""
    label = ModeIndicator.for_compose_skill("compose:review")
    assert "🔎" in label


def test_compose_unknown_skill() -> None:
    """未知技能 → [📦 name]."""
    label = ModeIndicator.for_compose_skill("compose:unknown")
    assert "📦" in label
    assert "compose:unknown" in label
