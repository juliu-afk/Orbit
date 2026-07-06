"""微信集成 Pydantic 模型——API 请求/响应与内部数据对象。

WHY 独立于 ORM 模型：Pydantic 用于 API 序列化/校验，
ORM 用于 SQLite 持久化，职责分离。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── 绑定 ──────────────────────────────────────────────

class BindStartResponse(BaseModel):
    """POST /wechat/bind/start 响应。"""
    bind_token: str
    qrcode_data_url: str  # data:image/png;base64,...
    expires_at: str  # ISO 8601


class BindStatusResponse(BaseModel):
    """GET /wechat/bind/status 响应。"""
    status: Literal["unbound", "pending", "active", "disconnected"]
    wechat_nickname: str | None = None
    connected_at: str | None = None


class CallbackRequest(BaseModel):
    """POST /wechat/callback 请求——iLink 服务器调用，不经 AuthMiddleware。"""
    openid: str
    bind_token: str


# ── 消息路由 ────────────────────────────────────────────

class WechatMessage(BaseModel):
    """来自微信的入站消息。"""
    openid: str
    content: str  # 原始文本（含 @Orbit 前缀）
    message_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageIntent(BaseModel):
    """消息意图分类结果。"""
    category: Literal["create_task", "query_task", "approve", "reject", "status", "help", "qa", "unknown"]
    task_id: str | None = None  # 查询/审批/拒绝时提取
    payload: str = ""  # 命令参数（如任务描述）


# ── 出站 ────────────────────────────────────────────────

class OutboundMessage(BaseModel):
    """待发送的出站消息。"""
    openid: str
    content: str
    priority: Literal["high", "normal", "low"] = "normal"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── 配置 ────────────────────────────────────────────────

class WechatConfig(BaseModel):
    """微信推送偏好配置。"""
    enabled: bool = True
    daily_summary_time: str = "09:00"  # HH:MM 格式
    quiet_hours_start: str | None = "22:00"
    quiet_hours_end: str | None = "08:00"

    def is_quiet_time(self) -> bool:
        """当前是否在静默时段内。"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        now = datetime.now().time()
        start_h, start_m = map(int, self.quiet_hours_start.split(":"))
        end_h, end_m = map(int, self.quiet_hours_end.split(":"))
        start = now.replace(hour=start_h, minute=start_m)
        end = now.replace(hour=end_h, minute=end_m)
        if start <= end:
            return start <= now <= end
        else:
            # 跨天时段（如 22:00 ~ 08:00）
            return now >= start or now <= end
