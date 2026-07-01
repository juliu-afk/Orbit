"""LLM 相关工厂——LLMRequest/LLMResponse/LLMUsage。

用于创建确定性的测试输入/输出，替代真实 LLM 调用。
"""

from __future__ import annotations

import uuid
from typing import Any

from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage

DEFAULT_SYSTEM_PROMPT = "你是 V14.1 多智能体协作网络中的执行 Agent，输出必须通过 L1-L8 验证。"


def create_llm_usage(
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    total_tokens: int | None = None,
    cost_usd: float = 0.0,
    **kwargs: Any,
) -> LLMUsage:
    """创建 LLMUsage——单次调用 Token 消耗。

    Args:
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        total_tokens: 总 token 数（None→自动计算）
        cost_usd: 美元成本
    """
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )


def create_llm_request(
    prompt: str = "测试需求：实现用户登录功能",
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    tools: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    provider: str | None = None,
    **kwargs: Any,
) -> LLMRequest:
    """创建 LLMRequest——LLM 调用请求。

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词（None→使用默认值）
        temperature: 温度（0.0-2.0）
        max_tokens: 最大输出 token
        tools: 工具 JSON Schema 列表
        messages: 完整消息历史（含 system/user/assistant/tool 角色）
        provider: LLM provider（None=自动检测）
    """
    return LLMRequest(
        prompt=prompt,
        system_prompt=system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        messages=messages,
        provider=provider,
    )


def create_llm_response(
    content: str = "```python\nprint('hello')\n```",
    model: str = "deepseek/deepseek-v4-pro",
    usage: LLMUsage | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    stop_reason: str | None = None,
    model_source: str = "default",
    degraded: bool = False,
    provider_adapter: str | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """创建 LLMResponse——LLM 调用响应。

    Args:
        content: LLM 输出内容
        model: 使用的模型名称
        usage: Token 消耗（None→自动创建默认值）
        tool_calls: 工具调用列表（OpenAI 格式）
        stop_reason: 停止原因（None→根据 tool_calls 自动设置）
        model_source: 模型选择来源
        degraded: 是否降级返回
        provider_adapter: 使用的 ProviderAdapter 名称
    """
    if usage is None:
        usage = create_llm_usage()
    if stop_reason is None:
        stop_reason = "tool_calls" if tool_calls else "end_turn"
    return LLMResponse(
        content=content,
        model=model,
        usage=usage,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        model_source=model_source,
        degraded=degraded,
        provider_adapter=provider_adapter,
    )
