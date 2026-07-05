"""蒸馏原则上下文构建器——从 DistillationEngine 注入可复用策略原则。

对标 Compound /ce-compound 复利闭环: 每次任务自动引用历史经验。
distill_from_trajectory → top_principles → system prompt 注入。

接入点: PromptBuilder 组装 system prompt 时调用。
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.evolution.distill import DistillationEngine


class PrinciplesContextBuilder:
    """蒸馏引擎 → Agent 上下文注入器。

    从 DistillationEngine 搜索与任务相关的策略原则，
    格式化为 markdown 段落供 system prompt 使用。

    fail-open: 蒸馏引擎不可用或原则为空 → 返回空上下文。
    """

    name = "principles"

    def __init__(self, engine: DistillationEngine | None = None) -> None:
        self._engine = engine

    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """搜索相关原则并格式化。

        Args:
            inputs: 含 task_description 的上下文字典

        Returns:
            {"principles_text": "## 历史经验（自动注入）\\n- [...] ..."}
            无原则时返回 {"principles_text": ""}
        """
        if self._engine is None:
            return {"principles_text": ""}

        task_desc = inputs.get("task_description", "")
        if not task_desc:
            return {"principles_text": ""}

        try:
            principles = self._engine.search(task_desc, limit=5)
        except Exception:
            return {"principles_text": ""}

        if not principles:
            return {"principles_text": ""}

        lines = ["## 历史经验（自动注入——来自过往任务蒸馏）"]
        for p in principles:
            lines.append(f"- [{p.category}] {p.principle}")

        return {"principles_text": "\n".join(lines)}
