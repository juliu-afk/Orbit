"""Agent 通信协议数据模型 (Step 5.4 PR #1).

定义 4 种通信模式: Request-Response / Notification / Streaming / Callback
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    STREAM_CHUNK = "stream_chunk"


class ResponseStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CIRCUIT_OPEN = "circuit_open"


class ErrorCode(StrEnum):
    """Agent 通信标准错误码。"""

    AGENT_UNAVAILABLE = "AGENT_001"  # 目标未注册/已下线
    AGENT_TIMEOUT = "AGENT_002"  # 请求超时
    AGENT_CIRCUIT_OPEN = "AGENT_003"  # 下游熔断开启
    AGENT_RATE_LIMITED = "AGENT_006"  # 下游限流


@dataclass
class Message:
    """消息基类——所有 Agent 间消息的公共字段。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = ""  # 关联原始请求 ID (Response/Stream 用)
    source_agent: str = ""
    target_agent: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "timestamp": self.timestamp,
        }


@dataclass
class Request(Message):
    """Request-Response 模式——同步等待响应。"""

    type: str = MessageType.REQUEST
    method: str = ""  # 调用方法名: verify / review / execute
    params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "type": self.type, "method": self.method, "params": self.params,
            "timeout_seconds": self.timeout_seconds, "retry_count": self.retry_count,
        })
        return d


@dataclass
class Response(Message):
    """Request 的响应——同步返回。"""

    type: str = MessageType.RESPONSE
    status: str = ResponseStatus.SUCCESS  # success | error | timeout | circuit_open
    result: Any = None
    error_code: str = ""
    error_message: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "type": self.type, "status": self.status, "result": self.result,
            "error_code": self.error_code, "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        })
        return d


@dataclass
class Notification(Message):
    """Fire-and-Forget 模式——发送后不等待响应。"""

    type: str = MessageType.NOTIFICATION
    event: str = ""  # 事件名: task_completed / agent_error / alert_triggered
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"type": self.type, "event": self.event, "payload": self.payload})
        return d


@dataclass
class StreamChunk(Message):
    """流式数据块——长耗时操作 (Z3/沙箱) 分块推送。"""

    type: str = MessageType.STREAM_CHUNK
    sequence: int = 0  # 序号, 从 0 开始
    data: str = ""  # 当前块数据
    is_last: bool = False  # 是否为最后一块
    error: str = ""  # 流式传输中的错误信息

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "type": self.type, "sequence": self.sequence,
            "data": self.data, "is_last": self.is_last, "error": self.error,
        })
        return d
