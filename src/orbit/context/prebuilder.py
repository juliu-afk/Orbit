"""ContextPrebuilder 基类 + 工厂 (Phase 2 Token节省, PR#201 审查修复)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class ContextPrebuilder(ABC):
    role: str = ""
    max_chars_per_field: int = 5000

    @abstractmethod
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]: ...

    def _truncate_field(self, value: str, max_chars: int | None = None) -> str:
        limit = max_chars or self.max_chars_per_field
        if len(value) <= limit:
            return value
        half = limit // 2
        cut = len(value) - limit
        return value[:half] + f"\n... [{cut} chars truncated] ...\n" + value[-half:]

    def _strip_keys(self, d: dict[str, Any], keys_to_remove: set[str]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k not in keys_to_remove}

    # PR#201 P2-1: 模块级缓存——Prebuilder 无状态
    _instances: dict[str, "ContextPrebuilder"] = {}

    @staticmethod
    def build_for_role(role: str) -> "ContextPrebuilder":
        if role in ContextPrebuilder._instances:
            return ContextPrebuilder._instances[role]
        from orbit.context.prebuilders.architect import ArchitectContextPrebuilder
        from orbit.context.prebuilders.clarifier import ClarifierContextPrebuilder
        from orbit.context.prebuilders.developer import DeveloperContextPrebuilder
        from orbit.context.prebuilders.qa import QAContextPrebuilder
        from orbit.context.prebuilders.reviewer import ReviewerContextPrebuilder
        mapping: dict[str, ContextPrebuilder] = {
            "clarifier": ClarifierContextPrebuilder(),
            "architect": ArchitectContextPrebuilder(),
            "developer": DeveloperContextPrebuilder(),
            "reviewer": ReviewerContextPrebuilder(),
            "qa": QAContextPrebuilder(),
            "chatter": ClarifierContextPrebuilder(),  # PR#201 P2-2: chatter→clarifier
        }
        instance = mapping.get(role, DeveloperContextPrebuilder())
        ContextPrebuilder._instances[role] = instance
        return instance
