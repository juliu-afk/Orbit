"""事件工厂——创建测试用 StreamEvent 和 DashboardEvent。

用于快速构造流式事件和仪表盘事件。
"""

from __future__ import annotations

import uuid
from typing import Any

from orbit.stream.events import StreamEvent, StreamEventType


def create_stream_event(
    event_type: str = "finish_step",
    agent_id: str = "developer",
    task_id: str = "",
    turn: int = 1,
    data: dict[str, Any] | None = None,
    **kwargs: Any,
) -> StreamEvent:
    """创建 StreamEvent——流式事件。

    Args:
        event_type: 事件类型（text_delta/thinking/tool_call/tool_result/turn_start/finish_step/error/cancelled）
        agent_id: Agent ID
        task_id: 任务 ID
        turn: ReAct 循环轮次
        data: 事件数据（按 event_type 有不同 shape）
    """
    if data is None:
        data = _default_data_for_type(event_type)

    return StreamEvent(
        type=StreamEventType(event_type),
        agent_id=agent_id,
        task_id=task_id or str(uuid.uuid4()),
        turn=turn,
        data=data,
    )


def create_text_delta(
    delta: str = "code",
    agent_id: str = "developer",
    task_id: str = "",
    turn: int = 1,
) -> StreamEvent:
    """快捷创建 TEXT_DELTA 事件。"""
    return create_stream_event(
        event_type="text_delta",
        agent_id=agent_id,
        task_id=task_id,
        turn=turn,
        data={"delta": delta},
    )


def create_tool_call_event(
    tool: str = "read_file",
    args: dict[str, Any] | None = None,
    agent_id: str = "developer",
    task_id: str = "",
    turn: int = 1,
) -> StreamEvent:
    """快捷创建 TOOL_CALL 事件。"""
    return create_stream_event(
        event_type="tool_call",
        agent_id=agent_id,
        task_id=task_id,
        turn=turn,
        data={"tool": tool, "args": args or {"path": "test.py"}},
    )


def create_tool_result_event(
    tool: str = "read_file",
    result_size: int = 1024,
    truncated: bool = False,
    agent_id: str = "developer",
    task_id: str = "",
    turn: int = 1,
) -> StreamEvent:
    """快捷创建 TOOL_RESULT 事件。"""
    return create_stream_event(
        event_type="tool_result",
        agent_id=agent_id,
        task_id=task_id,
        turn=turn,
        data={"tool": tool, "result_size": result_size, "truncated": truncated},
    )


def create_finish_step(
    output: str = "[mock] CODE_GENERATED_OK",
    turns: int = 3,
    tool_calls: int = 2,
    agent_id: str = "developer",
    task_id: str = "",
) -> StreamEvent:
    """快捷创建 FINISH_STEP 事件。"""
    return create_stream_event(
        event_type="finish_step",
        agent_id=agent_id,
        task_id=task_id,
        turn=turns,
        data={"output": output, "turns": turns, "tool_calls": tool_calls},
    )


def _default_data_for_type(event_type: str) -> dict[str, Any]:
    """按事件类型返回合理的默认 data。"""
    defaults = {
        "text_delta": {"delta": "test"},
        "thinking": {"content": "I need to think about this..."},
        "tool_call": {"tool": "read_file", "args": {"path": "test.py"}},
        "tool_result": {"tool": "read_file", "result_size": 1024, "truncated": False},
        "turn_start": {"turn": 1, "remaining_turns": 19},
        "finish_step": {"output": "[mock] OK", "turns": 3, "tool_calls": 2},
        "error": {"message": "mock error", "code": "MOCK_ERROR"},
        "cancelled": {"message": "用户取消"},
    }
    return defaults.get(event_type, {})
