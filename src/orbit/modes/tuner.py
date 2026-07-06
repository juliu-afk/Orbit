"""ModeTuner——mode 意图检测 + mode.yaml 写回.

检测用户在聊天中的 mode 调整意图:
  - 精确命令: /mode fast, /mode deep, /mode reset
  - 自然语言: "快点" "别问了" "太慢了" "问细点" "深入"

预设效果:
  fast:  max_questions_per_branch=8, question_strategy=breadth_first
  deep:  max_questions_per_branch=30, question_strategy=depth_first
  reset: 恢复 mode.yaml 到默认值
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

if TYPE_CHECKING:
    from orbit.modes.loader import ModeLoader
    from orbit.modes.schemas import ModeConfig

logger = structlog.get_logger("orbit.modes.tuner")


class ModePreset(StrEnum):
    """Mode 预设——用户可触发，对应不同的交互节奏."""

    FAST = "fast"    # 加速: 8 问题/分支 + 广度优先
    DEEP = "deep"    # 深入: 30 问题/分支 + 深度优先
    RESET = "reset"  # 恢复默认值


# ── 意图检测关键词 ─────────────────────────────
# WHY 精确命令优先: /mode 明确意图，自然语言只在无命令时匹配
_INTENT_PATTERNS: dict[ModePreset, list[str]] = {
    ModePreset.FAST: [
        "/mode fast", "/mode 快", "/mode 加速",
        "快点", "快一点", "加速", "太慢了", "别问了",
        "别啰嗦", "速战速决", "不要问那么多", "效率高点",
    ],
    ModePreset.DEEP: [
        "/mode deep", "/mode 深", "/mode 深入", "/mode 细",
        "问细点", "深入", "仔细", "详细", "慢点",
        "问详细", "多问点", "走深一点",
    ],
    ModePreset.RESET: [
        "/mode reset", "/mode 重置", "/mode 默认",
        "恢复默认", "回到默认", "恢复原来的", "用默认的",
    ],
}

# ── 预设参数 ──────────────────────────────────
# WHY dict 而非对象: 直接覆盖 mode.yaml behavior 字段，简单透明
_PRESET_PARAMS: dict[ModePreset, dict] = {
    ModePreset.FAST: {
        "max_questions_per_branch": 8,
        "question_strategy": "breadth_first",
    },
    ModePreset.DEEP: {
        "max_questions_per_branch": 30,
        "question_strategy": "depth_first",
    },
}

# 默认参数（reset 用）
_DEFAULT_PARAMS: dict = {
    "max_questions_per_branch": 20,
    "question_strategy": "depth_first",
    "require_recommendation": True,
    "codebase_first": True,
    "auto_upgrade_context": True,
}


class ModeTuner:
    """Mode 调优器——意图检测 + 写回."""

    @classmethod
    def detect_intent(cls, message: str) -> ModePreset | None:
        """检测消息中是否有 mode 调整意图.

        WHY 精确命令优先: /mode fast 比"快点做"更明确。
        自然语言仅在没有精确命令时匹配。
        """
        lower = message.strip().lower()

        # 先匹配精确命令
        for preset in (ModePreset.FAST, ModePreset.DEEP, ModePreset.RESET):
            cmd_patterns = [p for p in _INTENT_PATTERNS[preset] if p.startswith("/mode")]
            if any(cmd in lower for cmd in cmd_patterns):
                logger.info("mode_intent_detected", preset=preset.value, source="command")
                return preset

        # 再匹配自然语言
        for preset in (ModePreset.FAST, ModePreset.DEEP, ModePreset.RESET):
            nl_patterns = [p for p in _INTENT_PATTERNS[preset] if not p.startswith("/mode")]
            if any(nl in lower for nl in nl_patterns):
                logger.info("mode_intent_detected", preset=preset.value, source="natural_language")
                return preset

        return None

    @classmethod
    def apply_preset(
        cls,
        loader: "ModeLoader",
        mode_name: str,
        preset: ModePreset,
    ) -> "ModeConfig | None":
        """根据预设修改 mode.yaml 并写回磁盘.

        Args:
            loader: ModeLoader 实例
            mode_name: 目标 mode 名（如 "clarify"）
            preset: 预设类型

        Returns:
            新的 ModeConfig，失败返回 None
        """
        if preset == ModePreset.RESET:
            return cls._reset_mode(loader, mode_name)

        params = _PRESET_PARAMS.get(preset)
        if params is None:
            return None

        return cls._update_mode_file(loader, mode_name, params)

    @classmethod
    def _update_mode_file(
        cls,
        loader: "ModeLoader",
        mode_name: str,
        params: dict,
    ) -> "ModeConfig | None":
        """修改 mode.yaml 中 behavior 参数并写回.

        WHY 委托 loader.update_behavior(): tuner 不直接访问文件系统。
        """
        return loader.update_behavior(mode_name, params)

    @classmethod
    def _reset_mode(
        cls,
        loader: "ModeLoader",
        mode_name: str,
    ) -> "ModeConfig | None":
        """恢复 mode.yaml 到默认参数."""
        return cls._update_mode_file(loader, mode_name, _DEFAULT_PARAMS)
