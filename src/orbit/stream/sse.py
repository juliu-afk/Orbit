"""SSE 端点——流式 Agent 输出推送给驾驶舱（Phase 3 AC19.4-19.5）。

WHY SSE 而非 WebSocket: 流式 Agent 输出是单向的（Agent→前端），
SSE 比 WebSocket 更简单——零握手帧、自动重连、浏览器原生 EventSource。

取消是反向通道——走 POST endpoint，避免 SSE 双向协议复杂化。
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orbit.agents.factory import AgentFactory
from orbit.api.dependencies import verify_stream_token  # 5C.1
from orbit.stream.cancellation import CancellationToken

logger = structlog.get_logger()

router = APIRouter()

# 全局 token 注册表——task_id → CancellationToken
# WHY 全局: FastAPI 无状态，token 需要跨请求存活
_TOKENS: dict[str, CancellationToken] = {}


class AgentRunRequest(BaseModel):
    """启动 Agent 流式执行请求。"""

    task: str = Field(..., min_length=1, description="任务描述")
    role: str = Field("developer", description="Agent 角色")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文")


class AgentCancelRequest(BaseModel):
    """取消 Agent 执行请求。"""

    task_id: str = Field(..., min_length=1, description="任务 ID")


@router.post("/api/v1/agent/{agent_id}/run")
async def agent_run(agent_id: str, body: AgentRunRequest) -> dict[str, Any]:
    """启动 Agent 流式执行——返回 task_id。

    客户端收到 task_id 后连 GET /api/v1/agent/{agent_id}/stream?task_id=...
    """
    import uuid

    task_id = uuid.uuid4().hex[:12]
    # 预注册 token（Agent 尚未启动，客户端可提前取消）
    _TOKENS[task_id] = CancellationToken()

    return {
        "code": 0,
        "data": {"task_id": task_id, "agent_id": agent_id},
        "message": "ok",
    }


@router.get("/api/v1/agent/{agent_id}/stream")
async def agent_stream(
    agent_id: str,
    task_id: str,
    request: Request,
    llm: Any = None,
    tools: Any = None,
    _token: str = Depends(verify_stream_token),  # 5C.1
) -> StreamingResponse:
    """SSE 端点——流式推送 Agent 执行事件。

    GET /api/v1/agent/{agent_id}/stream?task_id=abc123
    → SSE (text/event-stream)
    """
    from orbit.agents.base import AgentInput, AgentRole

    # 获取或创建取消令牌
    token = _TOKENS.get(task_id, CancellationToken())
    _TOKENS[task_id] = token

    async def event_generator():
        try:
            # 创建 Agent
            role = (
                AgentRole(agent_id)
                if agent_id in AgentRole._value2member_map_
                else AgentRole.DEVELOPER
            )
            agent = AgentFactory.create(
                role=role,
                llm=llm,
                tools=tools,
                event_bus=None,  # SSE 替代 event_bus
            )

            input_data = AgentInput(
                task="",  # 从 context 取 task（实际由 POST /run 传入）
                context={"task_id": task_id},
                role=role,
            )

            # 从 query param 取 task（SSE 连接不传 body）
            # task 实际由之前的 POST /run 存储——简化：query 传 task
            input_data.task = request.query_params.get("task", "")

            async for event in agent.execute_stream(input_data, cancel_token=token):
                # SSE 格式: event: <type>\ndata: <json>\n\n
                event_type = event.type.value
                event_json = event.model_dump_json()
                yield f"event: {event_type}\ndata: {event_json}\n\n"

        except Exception as e:
            logger.error("sse_stream_error", error=str(e), task_id=task_id)
            error_data = json.dumps(
                {
                    "type": "error",
                    "task_id": task_id,
                    "data": {"message": str(e), "code": "SSE_ERROR"},
                }
            )
            yield f"event: error\ndata: {error_data}\n\n"

        finally:
            # 客户端断连时确保取消令牌——与 execute_stream finally 双重保险
            token.cancel()
            _TOKENS.pop(task_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 不缓冲
        },
    )


@router.post("/api/v1/agent/{agent_id}/cancel")
async def agent_cancel(agent_id: str, body: AgentCancelRequest) -> dict[str, Any]:
    """取消 Agent 执行。

    WHY POST 而非 SSE 反向通道: SSE 是单向协议，
    取消走独立 endpoint 更简单可靠。
    """
    token = _TOKENS.get(body.task_id)
    if token is None:
        return {
            "code": 404,
            "data": None,
            "message": f"task {body.task_id} 不存在或已完成",
        }
    token.cancel()
    return {
        "code": 0,
        "data": {"cancelled": True, "task_id": body.task_id},
        "message": "ok",
    }
