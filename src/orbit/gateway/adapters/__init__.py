"""ProviderAdapter——多 LLM provider schema 标准化基类。

对标 OpenClaw pi-tools.schema.ts 5 个 normalize 函数。
每个 provider 有独立 adapter，覆盖 normalize_tool_schema() 和 normalize_response()。

WHY ABC: 新 provider 只需写一个子类，不改 gateway 核心逻辑。
"""

from __future__ import annotations

from typing import Any


class ProviderAdapter:  # noqa: B024 (有意——基类提供默认 no-op，子类按需覆盖)
    """LLM provider schema 适配器基类。

    默认 no-op——子类只覆盖差异部分。
    """

    provider_name: str = "base"

    def normalize_tool_schema(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将工具 JSON Schema 标准化为该 provider 可接受的格式。

        默认透传——OpenAI 格式即是行业标准。
        Anthropic/OpenAI 兼容 OpenAI function calling format，
        Gemini/xAI 需要覆盖此方法。
        """
        return tools

    def normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """标准化消息历史格式。

        某些 provider 对 system/tool role 有特殊要求。
        """
        return messages

    def normalize_response(self, raw_response: Any, model: str) -> dict[str, Any]:
        """从 provider 原始响应中提取统一字段。

        Returns:
            {"content": str, "tool_calls": list|None, "stop_reason": str}
        """
        return {
            "content": "",
            "tool_calls": None,
            "stop_reason": "end_turn",
        }

    def normalize_stop_reason(self, finish_reason: str | None) -> str:
        """标准化 finish_reason 到 orbit 内部表示。

        end_turn | tool_calls | max_tokens | error
        """
        if finish_reason is None:
            return "end_turn"
        mapping = {
            "stop": "end_turn",
            "tool_calls": "tool_calls",
            "length": "max_tokens",
            "content_filter": "error",
        }
        return mapping.get(finish_reason, "end_turn")
