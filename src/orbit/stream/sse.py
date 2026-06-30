"""SSE 端点——流式 Agent 输出推送给驾驶舱（Phase 3 AC19.4-19.5）。

WHY SSE 而非 WebSocket: 流式 Agent 输出是单向的（Agent→前端），
SSE 比 WebSocket 更简单——零握手帧、自动重连、浏览器原生 EventSource。

取消是反向通道——走 POST endpoint，避免 SSE 双向协议复杂化。
"""

from __future__ import annotations

import json
import time
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

# 全局 token 注册表——task_id → (CancellationToken, created_at)
# WHY 全局: FastAPI 无状态，token 需要跨请求存活
# P0-13 (Issue#126): 加 created_at 时间戳支持 TTL 过期清理
_TOKENS: dict[str, tuple[CancellationToken, float]] = {}
_TOKEN_TTL_SECONDS: float = 300.0  # 5 分钟——未连接的 token 自动过期


def _cleanup_expired_tokens() -> int:
    """清理超过 TTL 的 token——返回清理数量。"""
    now = time.time()
    expired = [
        tid for tid, (_, ts) in _TOKENS.items() if now - ts > _TOKEN_TTL_SECONDS
    ]
    for tid in expired:
        _TOKENS.pop(tid, None)
    if expired:
        logger.info("sse_tokens_cleaned", count=len(expired))
    return len(expired)


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
    # P0-13 (Issue#126): 机会性清理过期条目，防内存泄漏
    # P2-3 (PR#133): 不是 periodic——仅在新任务创建时触发，长时间空闲仍有残留
    _cleanup_expired_tokens()
    # 预注册 token + 时间戳（Agent 尚未启动，客户端可提前取消）
    _TOKENS[task_id] = (CancellationToken(), time.time())

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

    # 获取或创建取消令牌（P0-13: 解包 (token, timestamp) 元组）
    _entry = _TOKENS.get(task_id)
    token = _entry[0] if _entry else CancellationToken()
    if task_id not in _TOKENS:
        _TOKENS[task_id] = (token, time.time())

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
    _entry = _TOKENS.get(body.task_id)
    if _entry is None:
        return {
            "code": 404,
            "data": None,
            "message": f"task {body.task_id} 不存在或已完成",
        }
    token, _ = _entry  # P0-13: 解包 (CancellationToken, timestamp)
    token.cancel()
    return {
        "code": 0,
        "data": {"cancelled": True, "task_id": body.task_id},
        "message": "ok",
    }
