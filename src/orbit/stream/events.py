"""流式事件模型。

对标 OpenCode runLoop 的 text-delta/tool-call/finish-step 事件。
每种事件有独立 data 结构，前端按 type 路由渲染。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class StreamEventType(StrEnum):
    """流式事件类型——对标 OpenCode prompt.ts:1400 fullStream events."""

    TEXT_DELTA = "text_delta"       # LLM 逐 token 输出
    THINKING = "thinking"           # LLM 思考过程（非工具推理）
    TOOL_CALL = "tool_call"         # Agent 决定调用工具
    TOOL_RESULT = "tool_result"     # 工具执行结果
    TURN_START = "turn_start"       # 新一轮 think→act→observe 开始
    FINISH_STEP = "finish_step"     # Agent 完成一步
    ERROR = "error"                 # 错误
    CANCELLED = "cancelled"         # 用户取消


class StreamEvent(BaseModel):
    """流式事件——async generator 的 yield 单元。

    data 字段按 event type 有不同 shape，用 dict 保持灵活——
    前端按 type dispatch 到不同 handler。
    """

    type: StreamEventType
    agent_id: str = ""
    task_id: str = ""
    turn: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    # TEXT_DELTA:  {"delta": "some text"}
    # THINKING:   {"content": "let me think..."}
    # TOOL_CALL:  {"tool": "read_file", "args": {"path": "..."}}
    # TOOL_RESULT: {"tool": "read_file", "result_size": 1024, "truncated": False}
    # TURN_START: {"turn": 3, "remaining_turns": 17}
    # FINISH_STEP: {"output": "...", "turns": 5, "tool_calls": 12}
    # ERROR:      {"message": "...", "code": "MAX_TURNS"}
    # CANCELLED:  {"message": "用户取消"}
