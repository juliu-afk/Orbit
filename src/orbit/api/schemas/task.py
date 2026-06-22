"""任务相关 Pydantic 模型（API 契约层）。

WHY 单独抽 schemas 包：接入层与领域层隔离，路由只依赖 schemas，
便于前端按 OpenAPI 契约并行开发，也便于后续换协议（gRPC 等）。
设计依据：PRD+ADR Step 1.1 数据契约（代码块-5/6）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, constr


class TaskState(StrEnum):
    """调度器状态机的所有状态。

    WHY 用 Enum 而非 str：路由/调度器/前端共用同一份状态定义，
    改动时编译期发现拼写错误，避免散落字符串硬编码。
    """

    IDLE = "IDLE"
    PARSING = "PARSING"
    PLANNING = "PLANNING"
    CODING = "CODING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskCreateRequest(BaseModel):
    """创建任务请求。

    - prd：产品需求文档，长度 10-5000 字符（Step 1.1 AC2：<10 返回 422）
    - language：目标语言，限制 4 种（后续可扩展）
    - callback_url：可选 webhook，任务完成时回调（V1 仅定义字段，不实现推送）
    """

    prd: constr(min_length=10, max_length=5000) = Field(..., description="产品需求文档")  # type: ignore[valid-type]
    language: Literal["python", "javascript", "java", "go"] = Field(
        "python", description="目标语言"
    )
    callback_url: HttpUrl | None = Field(None, description="可选回调 URL，任务完成时推送结果")


class TaskStatusResponse(BaseModel):
    """任务状态查询响应。

    task_id 用 uuid4 hex（Step 1.1 待定决议：去连字符缩短长度）。
    progress 0.0-1.0，调度器更新。
    """

    task_id: str = Field(..., pattern=r"^[0-9a-f]{32}$", description="UUID4 hex（无连字符）")
    state: TaskState
    progress: float = Field(ge=0.0, le=1.0)
    result: str | None = Field(None, description="任务产物（完成时填充）")
    created_at: datetime
    updated_at: datetime


class HTTPExceptionDetail(BaseModel):
    """统一错误响应体。

    WHY 所有 4xx/5xx 返回同一结构：前端错误处理逻辑统一，
    error_code 是稳定标识符（不随文案改动），便于客户端精确分支。
    """

    detail: str = Field(..., description="人类可读错误描述")
    error_code: str = Field(..., description="稳定错误码，如 TASK_NOT_FOUND")
    timestamp: datetime


class HealthResponse(BaseModel):
    """健康检查响应（AC1：/health 返回 status=ok）。"""

    status: str = Field("ok", description="服务状态")
    version: str = Field(..., description="版本号")
