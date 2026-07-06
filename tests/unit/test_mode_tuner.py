"""测试 ModeTuner——mode 意图检测 + 预设应用."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from orbit.modes.loader import ModeLoader
from orbit.modes.tuner import ModePreset, ModeTuner


# ════════════════════════════════════════════
# Fixture
# ════════════════════════════════════════════


@pytest.fixture
def clarify_loader() -> ModeLoader:
    """创建临时 mode 目录，含 clarify mode.yaml."""
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    mode_dir = root / "clarify"
    mode_dir.mkdir(parents=True)
    (mode_dir / "mode.yaml").write_text(
        yaml.dump({
            "name": "clarify",
            "version": 1,
            "description": "test",
            "applies_to": ["PARSING"],
            "behavior": {
                "question_strategy": "depth_first",
                "max_questions_per_branch": 20,
                "require_recommendation": True,
                "codebase_first": True,
                "auto_upgrade_context": True,
            },
            "references": [],
        }, allow_unicode=True),
        encoding="utf-8",
    )
    loader = ModeLoader(modes_dir=root)
    # 预加载到缓存
    loader.load("clarify")
    return loader


# ════════════════════════════════════════════
# 意图检测
# ════════════════════════════════════════════


def test_detect_command_fast() -> None:
    """精确命令 /mode fast → FAST."""
    assert ModeTuner.detect_intent("/mode fast") == ModePreset.FAST


def test_detect_command_deep() -> None:
    """精确命令 /mode deep → DEEP."""
    assert ModeTuner.detect_intent("/mode deep") == ModePreset.DEEP


def test_detect_command_reset() -> None:
    """精确命令 /mode reset → RESET."""
    assert ModeTuner.detect_intent("/mode reset") == ModePreset.RESET


def test_detect_natural_language_fast() -> None:
    """自然语言"快点" → FAST."""
    assert ModeTuner.detect_intent("能不能快点，别问那么多") == ModePreset.FAST


def test_detect_natural_language_deep() -> None:
    """自然语言"问细点" → DEEP."""
    assert ModeTuner.detect_intent("这个需求比较复杂，问细点") == ModePreset.DEEP


def test_detect_no_intent() -> None:
    """普通需求描述 → None."""
    assert ModeTuner.detect_intent("帮我做一个多币种折算功能") is None


def test_detect_command_priority() -> None:
    """精确命令优先于自然语言."""
    # "快点" 在自然语言中，但 "/mode deep" 优先
    result = ModeTuner.detect_intent("快点做，但是 /mode deep")
    assert result == ModePreset.DEEP  # 精确命令优先


# ════════════════════════════════════════════
# 预设应用
# ════════════════════════════════════════════


def test_apply_fast_preset(clarify_loader: ModeLoader) -> None:
    """FAST 预设: 8 问题 + 广度优先."""
    new_config = ModeTuner.apply_preset(clarify_loader, "clarify", ModePreset.FAST)
    assert new_config is not None
    assert new_config.behavior.max_questions_per_branch == 8
    assert new_config.behavior.question_strategy.value == "breadth_first"


def test_apply_deep_preset(clarify_loader: ModeLoader) -> None:
    """DEEP 预设: 30 问题 + 深度优先."""
    new_config = ModeTuner.apply_preset(clarify_loader, "clarify", ModePreset.DEEP)
    assert new_config is not None
    assert new_config.behavior.max_questions_per_branch == 30
    assert new_config.behavior.question_strategy.value == "depth_first"


def test_apply_reset_preset(clarify_loader: ModeLoader) -> None:
    """RESET 预设: 恢复默认 20 问题 + 深度优先."""
    # 先改成 FAST
    ModeTuner.apply_preset(clarify_loader, "clarify", ModePreset.FAST)
    # 再 reset
    new_config = ModeTuner.apply_preset(clarify_loader, "clarify", ModePreset.RESET)
    assert new_config is not None
    assert new_config.behavior.max_questions_per_branch == 20
    assert new_config.behavior.question_strategy.value == "depth_first"
