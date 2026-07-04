"""LLM 网关数据模型（Step 2.1）。

请求/响应/统计的结构化定义，供 LLMClient 和调度器使用。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """LLM 调用请求。"""

    prompt: str = Field(..., min_length=1, description="用户提示词")
    system_prompt: str = Field(
        "你是 V14.1 多智能体协作网络中的执行 Agent，输出必须通过 L1-L8 验证。",
        description="系统提示词（编排层风格，非个人能力描述）",
    )
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)
    # Phase 1: 工具调用支持（对标 OpenAI function calling）
    tools: list[dict] | None = Field(
        None, description="工具 JSON Schema 列表（OpenAI function calling 格式）"
    )
    tool_choice: str = Field("auto", description="工具选择策略: auto/none/required")
    # Phase 1: 消息历史（ReAct 循环用——支持多轮对话）
    messages: list[dict] | None = Field(
        None, description="完整消息历史（含 system/user/assistant/tool 角色）"
    )
    # Phase 3: 显式指定 provider 以选择 adapter（None = 自动从 model 推断）
    provider: str | None = Field(
        None, description="LLM provider: anthropic | openai | None(自动检测)"
    )
    # Inkeep 借鉴 #1: 任务类型——用于三层模型路由
    task_type: str | None = Field(
        None, description="reasoning | structured_output | summarization——用于自动模型选择"
    )


class LLMUsage(BaseModel):
    """单次调用的 Token 消耗与成本。"""

    prompt_tokens: int = Field(0, ge=0)
    completion_tokens: int = Field(0, ge=0)
    total_tokens: int = Field(0, ge=0)
    # WHY 按模型单价算成本：防幻觉 L3 熵监控和 Step 12 成本测算的基础数据
    cost_usd: float = Field(0.0, ge=0.0)


class LLMResponse(BaseModel):
    """LLM 调用响应。"""

    content: str
    model: str
    usage: LLMUsage
    # Step 2.3: 模型选择来源（"cc_switch_force" | "environment" | "cc_switch" | "router" | "default" | "fallback"）
    model_source: str = "default"
    # 熔断器触发时该字段为 True，表示本次是降级返回（非真实 LLM 输出）
    degraded: bool = False
    # Phase 1: 工具调用结果（ReAct 循环——LLM 请求调用工具）
    tool_calls: list[dict] | None = Field(
        None, description="LLM 返回的 tool_calls 列表（OpenAI 格式）"
    )
    stop_reason: str = Field(
        "end_turn", description="停止原因: end_turn | tool_calls | max_tokens | error"
    )
    # Phase 3: 记录应用的 adapter 名称（审计用）
    provider_adapter: str | None = Field(None, description="应用的 ProviderAdapter 名称")


class CircuitBreakerState(BaseModel):
    """熔断器状态（可序列化存 Redis）。"""

    failure_count: int = 0
    # OPEN 状态打开的时间戳（None 表示 CLOSED）
    opened_at: float | None = None
    # 半开状态标记
    half_open: bool = False
    # P1 LOG-4: 半开探测进行中——限制并发探测数
    probe_in_flight: bool = False
