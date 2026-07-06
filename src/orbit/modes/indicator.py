"""ModeIndicator——模式可见性前缀标签.

为 Agent 和 Compose 技能的回复生成可读的模式标签，
注入到首条 reply 前面，让用户知道当前谁在用什么策略。

输出示例:
  "[🔍 clarify·深度模式] 你的核心问题是什么？"
  "[📋 compose:plan] 分析 spec 后生成架构方案..."
"""

from __future__ import annotations


# ── 标签映射 ──────────────────────────────────

_AGENT_EMOJI: dict[str, str] = {
    "clarify": "🔍",
    "architect": "🏗️",
    "review": "🔎",
}

_STRATEGY_LABEL: dict[str, str] = {
    "depth_first": "深度模式",
    "breadth_first": "广角模式",
    "mixed": "混合模式",
}

_COMPOSE_EMOJI: dict[str, str] = {
    "compose:plan": "📋",
    "compose:review": "🔎",
    "compose:debug": "🐛",
    "compose:tdd": "🧪",
    "compose:verify": "✅",
    "compose:subagent": "🤖",
}

_FAST_LABEL = "快速模式"
_DEEP_LABEL = "深入模式"
_DEFAULT_LABEL = "默认"


class ModeIndicator:
    """模式前缀标签生成器——纯函数，零 IO."""

    @staticmethod
    def for_agent(
        mode_name: str | None,
        question_strategy: str = "depth_first",
        max_questions: int | None = None,
    ) -> str:
        """为 Agent 回复生成模式前缀.

        Args:
            mode_name: mode 名称（如 "clarify"），None→"默认"
            question_strategy: 提问策略（depth_first/breadth_first/mixed）
            max_questions: 每分支最大问题数，用于检测 fast/deep 预设

        Returns:
            "[🔍 clarify·深度模式]" 或 "[🔍 clarify·默认]"
        """
        if mode_name is None:
            mode_name = "clarify"
            strategy_label = "默认"
        else:
            # 检测预设级别
            if max_questions is not None:
                if max_questions <= 8:
                    strategy_label = _FAST_LABEL
                elif max_questions >= 30:
                    strategy_label = _DEEP_LABEL
                else:
                    strategy_label = _STRATEGY_LABEL.get(question_strategy, question_strategy)
            else:
                strategy_label = _STRATEGY_LABEL.get(question_strategy, question_strategy)

        emoji = _AGENT_EMOJI.get(mode_name, "🤖")
        return f"[{emoji} {mode_name}·{strategy_label}]"

    @staticmethod
    def for_compose_skill(skill_name: str) -> str:
        """为 Compose 技能回复生成前缀.

        Args:
            skill_name: 技能名（如 "compose:plan"）

        Returns:
            "[📋 compose:plan]"
        """
        emoji = _COMPOSE_EMOJI.get(skill_name, "📦")
        return f"[{emoji} {skill_name}]"
