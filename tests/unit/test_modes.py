"""测试 Mode File System——grill-me 交互协议层.

覆盖: ModeLoader 加载/校验/降级/缓存、ModeConfig 校验、references 按需加载.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from orbit.modes.loader import ModeLoader, ModeLoadError
from orbit.modes.schemas import BehaviorConfig, ModeConfig, QuestionStrategy


# ════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════


@pytest.fixture
def temp_modes_dir() -> Path:
    """创建临时 modes 目录，含 clarify/architect/review 三个内置 mode."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ["clarify", "architect", "review"]:
            mode_dir = root / name
            mode_dir.mkdir(parents=True)
            refs_dir = mode_dir / "references"
            refs_dir.mkdir()
            (mode_dir / "mode.yaml").write_text(
                yaml.dump({
                    "name": name,
                    "version": 1,
                    "description": f"Mode: {name}",
                    "applies_to": (
                        ["PARSING"] if name == "clarify"
                        else ["PLANNING"] if name == "architect"
                        else ["VERIFYING"]
                    ),
                    "behavior": {
                        "question_strategy": "depth_first",
                        "max_questions_per_branch": 20,
                        "require_recommendation": True,
                        "codebase_first": True,
                        "auto_upgrade_context": True,
                    },
                    "references": ["test-ref.md"],
                }, allow_unicode=True),
                encoding="utf-8",
            )
            # 创建 reference 文件
            (refs_dir / "test-ref.md").write_text("# Test Reference\n\nContent here.\n", encoding="utf-8")
        yield root


# ════════════════════════════════════════════
# ModeLoader 基础
# ════════════════════════════════════════════


def test_load_mode_success(temp_modes_dir: Path) -> None:
    """加载合法 mode.yaml → ModeConfig."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    mode = loader.load("clarify")
    assert mode is not None
    assert mode.name == "clarify"
    assert mode.version == 1
    assert mode.behavior.question_strategy == QuestionStrategy.DEPTH_FIRST
    assert mode.behavior.require_recommendation is True
    assert mode.behavior.codebase_first is True


def test_load_mode_missing_file(temp_modes_dir: Path) -> None:
    """mode.yaml 不存在 → 返回 None，不抛异常."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    mode = loader.load("nonexistent")
    assert mode is None  # 降级，不抛异常


def test_load_mode_cache(temp_modes_dir: Path) -> None:
    """同一 mode 二次加载 → 命中缓存."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    m1 = loader.load("clarify")
    m2 = loader.load("clarify")
    assert m1 is m2  # 同一对象（缓存命中）


def test_load_mode_invalid_yaml(temp_modes_dir: Path) -> None:
    """mode.yaml 格式错误 → 返回 None."""
    (temp_modes_dir / "broken" / "mode.yaml").parent.mkdir(exist_ok=True)
    (temp_modes_dir / "broken" / "mode.yaml").write_text(
        "::: not valid yaml :::", encoding="utf-8"
    )
    loader = ModeLoader(modes_dir=temp_modes_dir)
    mode = loader.load("broken")
    assert mode is None


# ════════════════════════════════════════════
# ModeLoader 高级
# ════════════════════════════════════════════


def test_list_modes(temp_modes_dir: Path) -> None:
    """列出所有含 mode.yaml 的子目录."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    modes = loader.list_modes()
    assert sorted(modes) == ["architect", "clarify", "review"]


def test_resolve_for_state(temp_modes_dir: Path) -> None:
    """根据状态机阶段匹配 mode."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    mode = loader.resolve_for_state("PARSING")
    assert mode is not None
    assert mode.name == "clarify"

    mode = loader.resolve_for_state("PLANNING")
    assert mode is not None
    assert mode.name == "architect"

    mode = loader.resolve_for_state("VERIFYING")
    assert mode is not None
    assert mode.name == "review"

    # 无匹配状态 → None
    mode = loader.resolve_for_state("UNKNOWN_STATE")
    assert mode is None


def test_load_reference(temp_modes_dir: Path) -> None:
    """按需加载 references/ 文件."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    ref = loader.load_reference("clarify", "test-ref.md")
    assert "Test Reference" in ref


def test_load_reference_missing(temp_modes_dir: Path) -> None:
    """reference 文件不存在 → 返回空字符串."""
    loader = ModeLoader(modes_dir=temp_modes_dir)
    ref = loader.load_reference("clarify", "nonexistent.md")
    assert ref == ""


# ════════════════════════════════════════════
# ModeConfig 校验
# ════════════════════════════════════════════


def test_mode_config_defaults() -> None:
    """ModeConfig 默认值——behavior 使用 BehaviorConfig 默认."""
    cfg = ModeConfig(name="test")
    assert cfg.name == "test"
    assert cfg.version == 1
    assert cfg.behavior.question_strategy == QuestionStrategy.DEPTH_FIRST
    assert cfg.behavior.max_questions_per_branch == 20


def test_behavior_config_validation() -> None:
    """BehaviorConfig 字段约束——max_questions_per_branch 范围 [1, 100]."""
    # 合法
    bc = BehaviorConfig(max_questions_per_branch=50)
    assert bc.max_questions_per_branch == 50

    # 超限 → Pydantic 校验失败
    with pytest.raises(Exception):
        BehaviorConfig(max_questions_per_branch=0)
    with pytest.raises(Exception):
        BehaviorConfig(max_questions_per_branch=200)


def test_question_strategy_values() -> None:
    """QuestionStrategy 枚举三个值."""
    assert QuestionStrategy.DEPTH_FIRST.value == "depth_first"
    assert QuestionStrategy.BREADTH_FIRST.value == "breadth_first"
    assert QuestionStrategy.MIXED.value == "mixed"
