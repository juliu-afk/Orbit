"""OpenAIAdapter——OpenAI provider schema 适配。

OpenAI function calling 是行业标准格式，Orbit 原生使用此格式。
本 adapter 大部分方法为 no-op 透传，保留为扩展点。

WHY 独立文件: 未来 OpenAI API 有 breaking change 时只需改此文件。
"""

from __future__ import annotations

from typing import Any

from orbit.gateway.adapters import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    """OpenAI API 适配器——大部分为透传。

    OpenAI function calling 格式即是 Orbit 原生格式，
    不需要 normalize_tool_schema 转换。
    """

    provider_name = "openai"

    def normalize_response(self, raw_response: Any, model: str) -> dict:
        """从 OpenAI litellm 响应提取统一字段。"""
        choice = raw_response.choices[0]
        content = choice.message.content or ""

        # 解析 tool_calls（原生 OpenAI 格式）
        tool_calls = None
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            tool_calls = []
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        finish = choice.finish_reason
        stop_reason = self.normalize_stop_reason(
            "tool_calls" if (tool_calls and not content) else finish
        )

        return {
            "content": content,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
        }
