"""AnthropicAdapter——Anthropic/Claude provider schema 适配。

Anthropic API 兼容 OpenAI function calling 格式（tool_use content block），
主要差异在 stop_reason 映射和 content block 结构。

WHY 独立文件: 未来 Anthropic API 有偏离时只需改此文件。
"""

from __future__ import annotations

from typing import Any

from orbit.gateway.adapters import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    """Anthropic Claude API 适配器。

    Anthropic 通过 litellm 调用时使用 OpenAI 兼容格式，
    本 adapter 处理 Anthropic 特有的响应结构差异。
    """

    provider_name = "anthropic"

    def normalize_response(self, raw_response: Any, model: str) -> dict[str, Any]:
        """从 Anthropic litellm 响应提取统一字段。

        litellm 已做大部分标准化——本方法处理残余差异。
        """
        choice = raw_response.choices[0]
        content = choice.message.content or ""

        # 解析 tool_calls（Anthropic 格式通过 litellm 已转为 OpenAI 格式）
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

        # Anthropic stop_reason: "end_turn" | "max_tokens" | "stop_sequence" | "tool_use"
        finish = choice.finish_reason
        stop_reason = self.normalize_stop_reason(
            "tool_calls" if (tool_calls and not content) else finish
        )

        return {
            "content": content,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
        }
