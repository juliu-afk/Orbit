"""API 依赖项——token认证 (5C.1)."""

from __future__ import annotations
from fastapi import HTTPException, Query

_STREAM_TOKEN = "orbit-local-stream"


def verify_stream_token(token: str = Query(...)) -> str:
    """SSE token认证——本地桌面工具简单共享密钥."""
    if token != _STREAM_TOKEN:
        raise HTTPException(status_code=403, detail="token 无效")
    return token
