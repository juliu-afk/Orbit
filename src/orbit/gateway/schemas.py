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
    # 熔断器触发时该字段为 True，表示本次是降级返回（非真实 LLM 输出）
    degraded: bool = False


class CircuitBreakerState(BaseModel):
    """熔断器状态（可序列化存 Redis）。"""

    failure_count: int = 0
    # OPEN 状态打开的时间戳（None 表示 CLOSED）
    opened_at: float | None = None
    # 半开状态标记
    half_open: bool = False
