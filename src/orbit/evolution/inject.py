"""策略原则自动注入器 (Phase E3).

WHY:
  DistillationEngine 存储策略原则但 Agent 不知道它们的存在。
  Injector 在 Agent 创建时自动查询高效用原则，注入 system prompt。

设计:
  - 在 AgentFactory.get_agent() 时调用
  - 查询 top N 高效用原则（min_utility=0.7）
  - 格式化为 markdown 块注入 prompt 末尾
  - 按 category 匹配（审计任务只注入审计原则）
"""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.evolution.distill import DistillationEngine

logger = structlog.get_logger("orbit.evolution.inject")

# 注入块的格式
INJECT_HEADER = "\n\n## 已验证的高效策略原则\n"
INJECT_FORMAT = "- {principle}\n"
INJECT_FOOTER = "\n请优先参考上述策略原则完成任务。"


class PromptInjector:
    """策略原则注入器——将高效用原则注入 Agent system prompt。

    用法:
        injector = PromptInjector(engine=distill_engine)
        enhanced_prompt = injector.inject(base_prompt, category="审计")
        # enhanced_prompt 末尾包含高效用的审计策略原则
    """

    DEFAULT_MIN_UTILITY = 0.6
    DEFAULT_MAX_PRINCIPLES = 5

    def __init__(self, engine: DistillationEngine | None = None) -> None:
        self._engine = engine
        self._stats: dict[str, int] = {}  # 注入计数

    def inject(
        self, base_prompt: str, category: str = "",
        min_utility: float = 0.0, max_principles: int = 0,
        task_keywords: list[str] | None = None,
    ) -> str:
        """将高效用策略原则注入 prompt。

        Args:
            base_prompt: 原始 system prompt
            category: 任务类别 ("审计"/"编码"/"测试")——用于过滤原则
            min_utility: 最低效用阈值（默认 DEFAULT_MIN_UTILITY）
            max_principles: 最多注入几条（默认 DEFAULT_MAX_PRINCIPLES）

        Returns:
            增强后的 prompt（追加策略原则块）
        """
        if self._engine is None:
            return base_prompt

        min_util = min_utility or self.DEFAULT_MIN_UTILITY
        max_n = max_principles or self.DEFAULT_MAX_PRINCIPLES

        # 查询高效用原则
        if category:
            search_query = category if task_keywords is None else f"{category} {' '.join(task_keywords)}"
        else:
            search_query = " ".join(task_keywords) if task_keywords else ""

        if search_query:
            principles = self._engine.search(search_query, limit=max_n)
        else:
            principles = self._engine.top_principles(limit=max_n)

        # 过滤低效用
        principles = [p for p in principles if p.utility_score >= min_util]

        if not principles:
            return base_prompt

        # 格式化注入块
        block = INJECT_HEADER
        for p in principles[:max_n]:
            block += INJECT_FORMAT.format(principle=p.principle)
        block += INJECT_FOOTER

        self._stats[category or "通用"] = self._stats.get(category or "通用", 0) + len(principles)
        logger.debug("principles_injected", category=category or "通用",
                     count=len(principles), avg_utility=sum(p.utility_score for p in principles)/len(principles))

        return base_prompt + block

    @property
    def total_injected(self) -> int:
        return sum(self._stats.values())
