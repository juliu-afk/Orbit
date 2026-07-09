"""LLM 网关数据模型（Step 2.1 + V15.1 多模态 P0）。

请求/响应/统计的结构化定义，供 LLMClient 和调度器使用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ── V15.1 多模态 P0：ContentBlock 类型 ──
# WHY 独立类型：Pydantic 校验拒绝非法 content type，避免无效请求发到 API


class TextContent(BaseModel):
    """文本块"""
    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """图片块——支持 HTTP URL 或 base64 data URI"""
    type: Literal["image_url"] = "image_url"
    image_url: dict  # {"url": "https://..." | "data:image/...;base64,..."}


class VideoContent(BaseModel):
    """视频块——支持 HTTP URL"""
    type: Literal["video_url"] = "video_url"
    video_url: dict  # {"url": "https://..."}


# 联合类型——content array 元素
ContentBlock = TextContent | ImageContent | VideoContent

# 图片最大大小：10MB base64 编码后约 13.3MB，设置 15MB 安全边界
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024


class LLMRequest(BaseModel):
    """LLM 调用请求。"""

    prompt: str = Field("", description="用户提示词（纯文本模式必填，多模态模式可选）")
    system_prompt: str = Field(
        "你是 V14.1 多智能体协作网络中的执行 Agent，输出必须通过 L1-L8 验证。",
        description="系统提示词（编排层风格，非个人能力描述）",
    )
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=16384)
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
    # ── V15.1 多模态 P0 ──
    # WHY content 独立字段：纯文本和纯文本的 str 值放 prompt；多模态的 list 放 content。
    # content 为 None → 走现有纯文本路径；非 None → 走多模态路径
    content: str | list[dict] | None = Field(
        None, description="多模态 content array（OpenAI 兼容格式）。为 None 时走现有纯文本路径"
    )
    # WHY tier 可手动指定：Agent 知道自己的任务复杂度时可显式指定，跳过自动检测
    tier: int | None = Field(
        None, ge=1, le=3, description="手动指定梯度（1=轻量/2=标准/3=重量）。None=自动检测"
    )

    @model_validator(mode="after")
    def _validate_prompt_or_content(self):
        """prompt 和 content 不能同时为空——至少有一个输入源。

        WHY model_validator：field_validator 中 content 字段可能尚未解析（定义顺序问题）。
        """
        if not self.prompt and self.content is None:
            raise ValueError("prompt 和 content 不能同时为空")
        return self

    @field_validator("content")
    @classmethod
    def _reject_oversized_images(cls, v):
        """内容校验——拒绝超大 base64 图片，避免 API 调用浪费。"""
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    img_url = item.get("image_url", {}).get("url", "")
                    if isinstance(img_url, str) and img_url.startswith("data:"):
                        # base64 编码膨胀率 ~4/3，检测长度
                        # 实际图片大小 ≈ (len(data_uri) - header) * 3/4
                        if len(img_url) > MAX_IMAGE_SIZE_BYTES:
                            raise ValueError(f"图片过大（>{MAX_IMAGE_SIZE_BYTES // (1024*1024)}MB），请压缩后重试")
        return v


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
