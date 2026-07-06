"""微信绑定管理——bind_token 生命周期 + 用户-OpenID 映射。

WHY 绑定令牌一次性+短期有效：防二维码被他人扫描后截获重用。
令牌 5 分钟过期，使用后立即销毁。
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger("orbit.wechat.bind")

BIND_TOKEN_EXPIRY_MINUTES = 5  # 绑定令牌有效期（分钟）


class BindManager:
    """管理 Orbit 用户与微信 OpenID 的绑定关系。

    绑定流程：
    1. create_bind_token(user_id) → 生成 QR 码 + 令牌
    2. verify_bind_token(token, openid) → 验证令牌，写入绑定
    3. unbind(user_id) → 断开绑定
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        # 内存缓存在 _pending_tokens: {bind_token: (user_id, expires_at)}
        self._pending_tokens: dict[str, tuple[int, datetime]] = {}

    # ── 令牌管理 ─────────────────────────────────────

    def create_bind_token(self, user_id: int) -> str:
        """生成一次性绑定令牌。返回 bind_token。"""
        # 清理该用户的旧待处理令牌
        self._cleanup_user_tokens(user_id)
        token = uuid.uuid4().hex + secrets.token_urlsafe(16)
        expires_at = datetime.now(UTC) + timedelta(minutes=BIND_TOKEN_EXPIRY_MINUTES)
        self._pending_tokens[token] = (user_id, expires_at)
        logger.info("bind_token_created", user_id=user_id, expires_at=expires_at.isoformat())
        return token

    def verify_bind_token(self, token: str, openid: str) -> int | None:
        """验证绑定令牌。成功返回 user_id，失败返回 None。

        WHY 一次性使用：验证成功后立即删除令牌，防重用。
        """
        # 清理已过期的令牌
        self._cleanup_expired()

        entry = self._pending_tokens.pop(token, None)
        if entry is None:
            logger.warning("bind_token_not_found", token_prefix=token[:8])
            return None

        user_id, expires_at = entry
        if datetime.now(UTC) > expires_at:
            logger.warning("bind_token_expired", user_id=user_id)
            return None

        logger.info("bind_verified", user_id=user_id, openid=openid)
        return user_id

    def has_pending_token(self, user_id: int) -> bool:
        """该用户是否有待处理的绑定令牌。"""
        self._cleanup_expired()
        return any(uid == user_id for uid, _ in self._pending_tokens.values())

    # ── 内部方法 ─────────────────────────────────────

    def _cleanup_user_tokens(self, user_id: int) -> None:
        """清理指定用户的所有待处理令牌。"""
        self._pending_tokens = {
            t: (uid, exp) for t, (uid, exp) in self._pending_tokens.items()
            if uid != user_id
        }

    def _cleanup_expired(self) -> None:
        """清理所有已过期令牌。"""
        now = datetime.now(UTC)
        self._pending_tokens = {
            t: (uid, exp) for t, (uid, exp) in self._pending_tokens.items()
            if exp > now
        }
