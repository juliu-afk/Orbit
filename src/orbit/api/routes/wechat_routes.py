"""微信集成 API 路由——绑定管理 + 配置。

WHY 路由层只做参数校验+响应格式化：遵循分层架构规则，
业务逻辑在 orbit.integration.wechat 模块。

WHY 无 user_id 参数：Orbit 是单用户桌面应用（token 认证），
整个实例只有一个绑定关系，用固定 ID=1 即可。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orbit.integration.wechat.bind import BindManager
from orbit.integration.wechat.channel import WechatChannel, WechatChannelUnavailableError
from orbit.integration.wechat.models import (
    CallbackRequest,
    WechatConfig,
)

router = APIRouter(prefix="/wechat", tags=["wechat"])

# 单用户——固定 user_id
_ORBIT_USER_ID = 1

# ── 模块级单例——由 create_app() 注入 ───────────────────
_bind_manager: BindManager | None = None
_channel: WechatChannel | None = None
# OpenID 映射（单用户，MVP 内存存储）
_bound_openid: str | None = None


def setup_wechat(bind_manager: BindManager, channel: WechatChannel) -> None:
    """注入微信模块依赖（由 create_app 调用）。"""
    global _bind_manager, _channel
    _bind_manager = bind_manager
    _channel = channel


def _get_bind_manager() -> BindManager:
    if _bind_manager is None:
        raise HTTPException(status_code=503, detail="微信服务未初始化")
    return _bind_manager


def _get_channel() -> WechatChannel:
    if _channel is None:
        raise HTTPException(status_code=503, detail="微信通道未就绪")
    return _channel


# ── 绑定端点 ──────────────────────────────────────────


@router.post("/bind/start")
async def bind_start() -> dict:
    """生成绑定 QR 码——驾驶舱展示给用户扫码。"""
    bm = _get_bind_manager()
    channel = _get_channel()

    # 检查是否已绑定
    if _bound_openid is not None:
        raise HTTPException(status_code=400, detail="WECHAT_001: 已绑定，请先断开")

    # 检查是否已有待处理令牌
    if bm.has_pending_token(_ORBIT_USER_ID):
        raise HTTPException(status_code=400, detail="WECHAT_001: 已有待处理绑定，请等待过期或刷新")

    # 生成令牌 + QR 码
    token = bm.create_bind_token(_ORBIT_USER_ID)
    try:
        qrcode_url = await channel.get_qrcode_data_url()
    except WechatChannelUnavailableError as e:
        raise HTTPException(status_code=503, detail=f"WECHAT_002: {e}")

    from datetime import UTC, datetime, timedelta
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    return {
        "code": 0,
        "data": {
            "bind_token": token,
            "qrcode_data_url": qrcode_url,
            "expires_at": expires_at.isoformat(),
        },
        "message": "ok",
    }


@router.get("/bind/status")
async def bind_status() -> dict:
    """查询微信绑定状态。"""
    bm = _get_bind_manager()

    if _bound_openid is not None:
        return {
            "code": 0,
            "data": {"status": "active", "wechat_nickname": None, "connected_at": None},
            "message": "ok",
        }

    if bm.has_pending_token(_ORBIT_USER_ID):
        return {
            "code": 0,
            "data": {"status": "pending", "wechat_nickname": None, "connected_at": None},
            "message": "ok",
        }

    return {
        "code": 0,
        "data": {"status": "unbound", "wechat_nickname": None, "connected_at": None},
        "message": "ok",
    }


@router.post("/callback")
async def wechat_callback(body: CallbackRequest) -> dict:
    """iLink 回调——微信扫码后调用。不经 AuthMiddleware。

    WHY /callback 需加入公开路径：iLink 服务器无法提供 X-Orbit-Token。
    """
    global _bound_openid
    bm = _get_bind_manager()

    user_id = bm.verify_bind_token(body.bind_token, body.openid)
    if user_id is None:
        raise HTTPException(status_code=400, detail="WECHAT_004: 绑定令牌无效或已过期")

    # 已绑定检查
    if _bound_openid is not None and _bound_openid != body.openid:
        raise HTTPException(status_code=400, detail="WECHAT_005: 该微信号已绑定其他账号")

    _bound_openid = body.openid
    return {"code": 0, "data": {"success": True}, "message": "绑定成功"}


@router.delete("/bind")
async def bind_delete() -> dict:
    """断开微信绑定。"""
    global _bound_openid
    _bound_openid = None
    return {"code": 0, "data": None, "message": "已断开微信绑定"}


# ── 配置端点（P2）─────────────────────────────────────

_config = WechatConfig()


@router.get("/config")
async def get_wechat_config() -> dict:
    return {"code": 0, "data": _config.model_dump(), "message": "ok"}


@router.put("/config")
async def update_wechat_config(config: WechatConfig) -> dict:
    global _config
    _config = config
    return {"code": 0, "data": _config.model_dump(), "message": "配置已更新"}
