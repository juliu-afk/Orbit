"""Agent 消息总线 (Step 5.4 PR #1).

asyncio 实现——Agent 注册/请求/通知/流式/回调 4 种通信模式。
幂等去重 + 超时 + 熔断传播 + 审计记录。
"""

from __future__ import annotations

import asyncio
import collections.abc
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import structlog

from orbit.communication.protocol import (
    ErrorCode,
    Message,
    Notification,
    Request,
    Response,
    ResponseStatus,
    StreamChunk,
)

logger = structlog.get_logger("orbit.communication")

DEFAULT_TIMEOUT = 30  # 默认请求超时（秒）
MAX_PENDING_REQUESTS = 256  # 最大未完成请求数
IDEMPOTENT_CACHE_SIZE = 200  # 幂等去重缓存大小


class AgentUnavailableError(Exception):
    """目标 Agent 未注册或已下线 (AGENT_001)。"""


class AgentTimeoutError(Exception):
    """请求超时 (AGENT_002)。"""


class AgentCircuitOpenError(Exception):
    """下游熔断开启 (AGENT_003)。"""


# Agent handler 类型: (Request) -> Response
AgentHandler = Callable[[Request], Response | asyncio.Future[Response]]


class AgentMessageBus:
    """Agent 消息总线——进程内 asyncio 实现。

    用法:
        bus = AgentMessageBus()
        bus.register("QAAgent", qa_handler)

        # Request-Response
        resp = await bus.request(Request(
            source_agent="Dev", target_agent="QA",
            method="verify", params={"code": "..."},
        ))

        # Fire-and-Forget
        bus.notify(Notification(
            source_agent="Dev", event="task_completed",
            payload={"task_id": "t1"},
        ))

        # Streaming
        async for chunk in bus.stream(Request(
            source_agent="Dev", target_agent="Sandbox",
            method="execute", params={"script": "..."},
        )):
            print(chunk.data)
    """

    def __init__(self) -> None:
        # Agent 注册表: name -> handler
        self._agents: dict[str, AgentHandler] = {}
        # 未完成请求: request_id -> asyncio.Future
        self._pending: dict[str, asyncio.Future[Response]] = {}
        # 幂等缓存: request_id -> Response (环形缓冲)
        self._idempotent_cache: dict[str, Response] = {}
        self._idempotent_keys: deque[str] = deque(maxlen=IDEMPOTENT_CACHE_SIZE)
        # 熔断状态: agent_name -> bool (True=OPEN)
        self._circuit_open: dict[str, bool] = {}
        # 审计记录
        self._audit: list[dict[str, Any]] = []

    # ── Agent 管理 ────────────────────────────────────────

    def register(self, name: str, handler: AgentHandler) -> None:
        """注册 Agent 处理器。"""
        self._agents[name] = handler
        logger.info("agent_registered", name=name)

    def unregister(self, name: str) -> None:
        """注销 Agent。"""
        self._agents.pop(name, None)
        # 取消该 Agent 的所有未完成请求
        to_cancel = [rid for rid, fut in self._pending.items()
                     if rid.startswith(f"{name}:")]
        for rid in to_cancel:
            fut = self._pending.pop(rid, None)
            if fut and not fut.done():
                fut.set_exception(AgentUnavailableError(f"Agent {name} 已下线"))

    def set_circuit_open(self, agent_name: str, open_state: bool) -> None:
        """设置 Agent 熔断状态（由熔断器调用）。"""
        self._circuit_open[agent_name] = open_state

    # ── Request-Response ──────────────────────────────────

    async def request(self, req: Request) -> Response:
        """同步 Request-Response——等待目标 Agent 响应。

        特性: 幂等去重 / 超时 / 熔断检查 / 审计记录
        """
        # 幂等检查
        if req.id in self._idempotent_cache:
            return self._idempotent_cache[req.id]

        # 检查目标是否存在
        if req.target_agent not in self._agents:
            self._record_audit(req, status="agent_unavailable")
            raise AgentUnavailableError(
                f"Agent {req.target_agent} 未注册", ErrorCode.AGENT_UNAVAILABLE
            )

        # 熔断检查
        if self._circuit_open.get(req.target_agent, False):
            resp = Response(
                id=f"resp-{req.id}",
                correlation_id=req.id,
                source_agent=req.target_agent,
                target_agent=req.source_agent,
                timestamp=time.time(),
                status=ResponseStatus.CIRCUIT_OPEN,
                error_code=ErrorCode.AGENT_CIRCUIT_OPEN,
                error_message=f"Agent {req.target_agent} 熔断开启",
            )
            self._cache_idempotent(req.id, resp)
            self._record_audit(req, status="circuit_open")
            return resp  # WHY 返回 Response 而非抛异常: 调用方可统一处理降级

        # 创建 Future 等待响应
        timeout = req.timeout_seconds or DEFAULT_TIMEOUT
        future: asyncio.Future[Response] = asyncio.get_event_loop().create_future()
        self._pending[req.id] = future

        # 异步投递请求给目标 Agent
        try:
            asyncio.create_task(self._deliver_request(req))
        except Exception:
            self._pending.pop(req.id, None)
            raise

        # 等待响应或超时
        try:
            resp = await asyncio.wait_for(future, timeout=timeout)
            self._cache_idempotent(req.id, resp)
            self._record_audit(req, status=resp.status)
            return resp
        except TimeoutError as e:
            self._pending.pop(req.id, None)
            self._record_audit(req, status="timeout")
            raise AgentTimeoutError(
                f"请求 {req.id} 超时 ({timeout}s)", ErrorCode.AGENT_TIMEOUT
            ) from e

    async def _deliver_request(self, req: Request) -> None:
        """投递请求给目标 Agent 并收集响应。"""
        handler = self._agents.get(req.target_agent)
        if handler is None:
            return

        start = time.time()
        try:
            result = handler(req)
            # 支持同步和异步 handler
            if asyncio.isfuture(result):
                result = await result
            # 如果 handler 返回 Response, 直接使用; 否则包装
            if isinstance(result, Response):
                resp = result
                resp.duration_ms = (time.time() - start) * 1000
            else:
                resp = Response(
                    id=f"resp-{req.id}",
                    correlation_id=req.id,
                    source_agent=req.target_agent,
                    target_agent=req.source_agent,
                    timestamp=time.time(),
                    status=ResponseStatus.SUCCESS,
                    result=result if isinstance(result, dict) else {"value": str(result)},
                    duration_ms=(time.time() - start) * 1000,
                )
        except Exception as e:
            resp = Response(
                id=f"resp-{req.id}",
                correlation_id=req.id,
                source_agent=req.target_agent,
                target_agent=req.source_agent,
                timestamp=time.time(),
                status=ResponseStatus.ERROR,
                error_message=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

        # 解析 Future
        fut = self._pending.pop(req.id, None)
        if fut and not fut.done():
            fut.set_result(resp)

    # ── Fire-and-Forget ───────────────────────────────────

    def notify(self, notif: Notification) -> None:
        """Fire-and-Forget——发送后不等待响应。

        广播给所有注册 Agent (除 source 自身)。
        """
        notif.timestamp = time.time()
        for name in list(self._agents.keys()):
            # 通知不设 target——广播所有 Agent
            asyncio.create_task(self._deliver_notification(notif, name))
        self._record_audit(notif, status="sent")

    async def _deliver_notification(self, notif: Notification, agent_name: str) -> None:
        """投递通知给单个 Agent。"""
        handler = self._agents.get(agent_name)
        if handler is None:
            return
        try:
            # 将 Notification 转为 Request 调用 handler
            req = Request(
                id=notif.id,
                source_agent=notif.source_agent,
                target_agent=agent_name,
                method=f"on_{notif.event}",
                params=notif.payload,
            )
            result = handler(req)
            if asyncio.isfuture(result):
                await result
        except Exception:
            logger.debug("notification_delivery_error", agent=agent_name, event=notif.event)

    # ── Streaming ─────────────────────────────────────────

    async def stream(self, req: Request) -> collections.abc.AsyncIterator[StreamChunk]:
        """流式推送——长耗时操作分块返回。

        用法:
            async for chunk in bus.stream(req):
                if chunk.is_last:
                    break
        """
        # 检查目标
        if req.target_agent not in self._agents:
            yield StreamChunk(
                sequence=0, is_last=True,
                error=f"Agent {req.target_agent} 未注册",
                source_agent=req.target_agent, target_agent=req.source_agent,
            )
            return

        # 熔断检查
        if self._circuit_open.get(req.target_agent, False):
            yield StreamChunk(
                sequence=0, is_last=True,
                error="AGENT_003: 熔断开启",
                source_agent=req.target_agent, target_agent=req.source_agent,
            )
            return

        # 创建队列收集流式块
        queue: asyncio.Queue[StreamChunk] = asyncio.Queue()
        asyncio.create_task(self._handle_stream(req, queue))

        seq = 0
        while True:
            chunk = await queue.get()
            chunk.sequence = seq
            seq += 1
            yield chunk
            if chunk.is_last:
                break

    async def _handle_stream(self, req: Request, queue: asyncio.Queue[StreamChunk]) -> None:
        """处理流式请求——调用 handler 并将结果转为 StreamChunk。"""
        handler = self._agents.get(req.target_agent)
        if handler is None:
            return
        try:
            result = handler(req)
            if asyncio.isfuture(result):
                result = await result
            # 将结果包装为单个 StreamChunk (后续可扩展为多次推送)
            content = str(result) if not isinstance(result, str) else result
            await queue.put(StreamChunk(
                data=content, is_last=True,
                source_agent=req.target_agent, target_agent=req.source_agent,
                timestamp=time.time(),
            ))
        except Exception as e:
            await queue.put(StreamChunk(
                is_last=True, error=str(e),
                source_agent=req.target_agent, target_agent=req.source_agent,
            ))

    # ── 查询 ──────────────────────────────────────────────

    def is_registered(self, name: str) -> bool:
        return name in self._agents

    def get_audit(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def get_queue_status(self) -> dict[str, int]:
        return {"pending_requests": len(self._pending), "registered_agents": len(self._agents)}

    # ── 内部 ──────────────────────────────────────────────

    def _cache_idempotent(self, request_id: str, resp: Response) -> None:
        """缓存响应——幂等去重。"""
        self._idempotent_cache[request_id] = resp
        self._idempotent_keys.append(request_id)

    def _record_audit(self, msg: Message, status: str = "") -> None:
        entry: dict[str, Any] = {
            "message_id": msg.id,
            "type": msg.type if hasattr(msg, "type") else "unknown",
            "source": msg.source_agent,
            "target": msg.target_agent,
            "status": status,
            "timestamp": time.time(),
        }
        self._audit.append(entry)
        # 环形缓冲
        if len(self._audit) > 500:
            self._audit = self._audit[-500:]
