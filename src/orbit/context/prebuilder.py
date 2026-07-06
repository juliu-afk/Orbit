"""ContextPrebuilder 基类 + 工厂 (Phase 2 Token节省).

Agent dispatch 前按角色裁剪 context——确定性预处理，0 LLM 调用。
与已有压缩管线正交：预构建改 TaskContext，L1-L5 改 messages 列表。

WHY: 报告核心原则——"确定性工具做筛选、定位、摘要 → LLM 只处理需要判断的部分"。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextPrebuilder(ABC):
    """上下文预构建器基类。

    每个 Agent 角色一个子类。纯 Python——无 IO、无 LLM 调用、无副作用。
    异常时 fail-open：调用方捕获异常后回退到原始 context。
    """

    role: str = ""  # 子类覆盖——对应 AgentRole.value
    max_chars_per_field: int = 5000  # 与 PromptBuilder/TaskContext 一致

    # P2: Prebuilder 实例缓存——首次创建后复用，避免每次 build_for_role() 新建 5 个实例
    _instances: dict[str, ContextPrebuilder] = {}

    @abstractmethod
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        """裁剪 context dict——返回裁剪后的 dict。

        Args:
            raw_context: TaskContext.to_dict() 的原始输出

        Returns:
            裁剪后的 dict——字段数 ≤ 输入，无关字段已删除，超大字段已截断
        """
        ...

    def _truncate_field(self, value: str, max_chars: int | None = None) -> str:
        """截断超长字符串——保留头尾，中间插入摘要标记。

        WHY head+tail 而非纯截断：保留开头（通常是关键信息）和结尾（结论/状态），
        中间丢弃部分用标记说明——Agent 仍能理解上下文。
        """
        limit = max_chars or self.max_chars_per_field
        if len(value) <= limit:
            return value
        half = limit // 2
        cut = len(value) - limit
        return value[:half] + f"\n... [{cut} chars truncated] ...\n" + value[-half:]

    def _strip_keys(self, d: dict[str, Any], keys_to_remove: set[str]) -> dict[str, Any]:
        """删除指定 key（浅层——仅第一级）。

        WHY 浅层删除：TaskContext 的 L1-L5 结构固定，不需要深层递归。
        """
        return {k: v for k, v in d.items() if k not in keys_to_remove}

    @staticmethod
    def build_for_role(role: str) -> ContextPrebuilder:
        """工厂方法——按角色字符串返回对应预构建器。

        延迟导入避免循环依赖——子类在首次调用时才加载。
        """
        # 延迟导入——ContextPrebuilder 子类在 prebuilders/ 下
        from orbit.context.prebuilders.architect import ArchitectContextPrebuilder  # noqa: F401
        from orbit.context.prebuilders.clarifier import ClarifierContextPrebuilder  # noqa: F401
        from orbit.context.prebuilders.developer import DeveloperContextPrebuilder  # noqa: F401
        from orbit.context.prebuilders.qa import QAContextPrebuilder  # noqa: F401
        from orbit.context.prebuilders.reviewer import ReviewerContextPrebuilder  # noqa: F401

        mapping: dict[str, ContextPrebuilder] = {}

        # P2: 检查缓存——首次创建后复用实例
        for role_key, cls in [
            ("clarifier", ClarifierContextPrebuilder),
            ("architect", ArchitectContextPrebuilder),
            ("developer", DeveloperContextPrebuilder),
            ("reviewer", ReviewerContextPrebuilder),
            ("qa", QAContextPrebuilder),
        ]:
            if role_key not in ContextPrebuilder._instances:
                ContextPrebuilder._instances[role_key] = cls()
            mapping[role_key] = ContextPrebuilder._instances[role_key]
        mapping["chatter"] = mapping["developer"]  # chatter 用 developer 规则
        return mapping.get(role, DeveloperContextPrebuilder())
