"""执行上下文——thread-local 存储 mode + 会话确认状态。

WHY thread-local: FastAPI 每个请求可能在不同线程处理，
但同一请求内的 Agent 执行链需要共享 mode 状态。
ReActAgent 的 tool dispatch 通过此模块读取当前 ChatMode
而无需修改所有 Agent 的接口。

Usage:
    from orbit.core.context import get_context, set_context
    ctx = get_context()
    ctx.chat_mode  # ChatMode.AUTO (default)
    set_context(chat_mode=ChatMode.PLAN, session_id="sess_1")
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from orbit.skills.models import ChatMode


@dataclass
class ExecutionContext:
    """单次请求的执行上下文——ChatMode + 会话确认状态。

    confirmed_tools: Edit Automatically 模式下用户已"记住"的工具集合。
                    只会话级——WebSocket 断连即清空。
    last_confirm_time: 上一次弹确认的时间戳——Manual 模式防抖用。
    """

    chat_mode: ChatMode = ChatMode.AUTO
    session_id: str = ""
    confirmed_tools: set[str] = field(default_factory=set)
    last_confirm_time: dict[str, float] = field(default_factory=dict)
    # compose 进度推送回调——聊天框流式输出编排进度
    stream_callback: object | None = None


# thread-local 存储——每个请求独立
_ctx = threading.local()


def get_context() -> ExecutionContext:
    """获取当前线程的执行上下文。无则创建默认（AUTO 模式）。"""
    if not hasattr(_ctx, "value"):
        _ctx.value = ExecutionContext()
    return _ctx.value


def set_context(
    chat_mode: ChatMode | None = None,
    session_id: str | None = None,
    confirmed_tools: set[str] | None = None,
    stream_callback: object | None = None,
) -> ExecutionContext:
    """部分更新执行上下文——只改传入的字段，其余保留原值。

    WHY 部分更新: 不同层注入不同字段——
    chat.py 注入 chat_mode + session_id，
    ToolRegistry 注入 confirmed_tools，
    不互相覆盖。
    """
    ctx = get_context()
    if chat_mode is not None:
        ctx.chat_mode = chat_mode
    if session_id is not None:
        ctx.session_id = session_id
    if confirmed_tools is not None:
        ctx.confirmed_tools = confirmed_tools
    if stream_callback is not None:
        ctx.stream_callback = stream_callback
    return ctx


def reset_context() -> None:
    """重置当前线程上下文——请求结束时调用。"""
    _ctx.value = ExecutionContext()
