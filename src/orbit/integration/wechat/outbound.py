"""微信出站队列——TokenBucket 频率控制 + 串行发送。

WHY 频率控制：微信对消息发送频率有限制，过量推送触发风控可能导致封号。
TokenBucket：5 条/分钟，30 条/小时，超出排队（超时 30s 丢弃）。

WHY 串行发送且间隔 ≥200ms：并发发送多条消息可能被微信服务器聚合或丢弃。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable

import structlog

from orbit.integration.wechat.models import OutboundMessage

logger = structlog.get_logger("orbit.wechat.outbound")

# ── 频率限制 ────────────────────────────────────────────
MAX_PER_MINUTE = 5
MAX_PER_HOUR = 30
MIN_INTERVAL_MS = 200  # 最小发送间隔（毫秒）
QUEUE_TIMEOUT_S = 30  # 队列超时（秒）


class TokenBucket:
    """令牌桶——控制发送频率。"""

    def __init__(self, per_minute: int = MAX_PER_MINUTE, per_hour: int = MAX_PER_HOUR) -> None:
        self._per_minute = per_minute
        self._per_hour = per_hour
        self._minute_timestamps: deque[float] = deque()
        self._hour_timestamps: deque[float] = deque()

    def can_send(self) -> bool:
        """当前是否可以发送。"""
        now = time.monotonic()
        # 清理过期时间戳
        while self._minute_timestamps and now - self._minute_timestamps[0] > 60:
            self._minute_timestamps.popleft()
        while self._hour_timestamps and now - self._hour_timestamps[0] > 3600:
            self._hour_timestamps.popleft()
        return (
            len(self._minute_timestamps) < self._per_minute
            and len(self._hour_timestamps) < self._per_hour
        )

    def record_send(self) -> None:
        """记录一次发送。"""
        now = time.monotonic()
        self._minute_timestamps.append(now)
        self._hour_timestamps.append(now)


# ── 处理器类型 ─────────────────────────────────────────
AsyncSendFn = Callable[[str, str], asyncio.Future[None] | None]
# 兼容同步和异步发送函数
SendFn = Callable[[str, str], None] | AsyncSendFn


class OutboundQueue:
    """出站消息队列——优先级排序 + 频率控制 + 串行发送。

    用法:
        queue = OutboundQueue(send_fn=channel.send_message)
        queue.start()
        queue.enqueue(OutboundMessage(...))
    """

    def __init__(self, send_fn: SendFn) -> None:
        self._send_fn = send_fn
        self._bucket = TokenBucket()
        self._queue: deque[OutboundMessage] = deque()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def enqueue(self, msg: OutboundMessage) -> None:
        """入队消息。按 priority 排序——high 在前。"""
        if msg.priority == "high":
            self._queue.appendleft(msg)
        else:
            self._queue.append(msg)
        logger.debug("wechat_outbound_queued", priority=msg.priority)

    async def start(self) -> None:
        """启动消费循环。"""
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("wechat_outbound_started")

    async def stop(self) -> None:
        """停止消费循环。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("wechat_outbound_stopped")

    async def _consume_loop(self) -> None:
        """消费循环——从队列取消息，等令牌，发送。"""
        while self._running:
            try:
                if not self._queue:
                    await asyncio.sleep(0.5)
                    continue

                msg = self._queue[0]
                # 检查超时
                age = (asyncio.get_event_loop().time() - msg.created_at.timestamp())
                if age > QUEUE_TIMEOUT_S:
                    self._queue.popleft()
                    logger.warning("wechat_outbound_timeout", openid=msg.openid)
                    continue

                # 等待令牌
                if not self._bucket.can_send():
                    await asyncio.sleep(1.0)
                    continue

                # 发送
                msg = self._queue.popleft()
                # 拆分长消息（600 汉字/条，按 Unicode 边界）
                chunks = self._split_message(msg.content)
                for chunk in chunks:
                    self._bucket.record_send()
                    # 兼容 async 和 sync 发送函数
                    result = self._send_fn(msg.openid, chunk)
                    if asyncio.iscoroutine(result):
                        await result
                    await asyncio.sleep(MIN_INTERVAL_MS / 1000)

            except Exception as e:
                logger.error("wechat_outbound_error", error=str(e))
                await asyncio.sleep(1.0)

    # ── 消息拆分 ─────────────────────────────────────

    @staticmethod
    def _split_message(content: str, max_chars: int = 600) -> list[str]:
        """按 Unicode codepoint 边界拆分长消息。

        WHY codepoint 边界而非字节边界：中文在 UTF-8 中占 3 字节，
        Emoji 占 4 字节，按字节切分可能截断字符导致乱码。
        Python 3 str 以 codepoint 为单位，len() + 切片天然安全。
        """
        if len(content) <= max_chars:
            return [content]
        return [content[i:i + max_chars] for i in range(0, len(content), max_chars)]


# ── 事件订阅——连接调度器事件到微信推送 ─────────────────

def setup_wechat_subscribers(
    event_bus,  # EventBus
    outbound_queue: OutboundQueue,
    get_openid_for_user: Callable[[int], str | None],
) -> None:
    """注册微信推送的事件订阅者。

    WHY 独立函数而非 OutboundQueue 方法：订阅逻辑属于集成层，
    不是队列职责。队列只负责"发送"，不负责"何时发送什么"。
    """

    async def on_task_update(event) -> None:
        """任务状态变更 → 判断是否需要推送微信。"""
        payload = event.payload
        state = payload.get("state", "")
        task_id = payload.get("task_id", "")
        task_name = payload.get("name", f"#{task_id}")

        # 仅推送完成和失败
        if state == "completed":
            text = f"✅ #{task_id} {task_name} 已完成"
        elif state == "failed":
            error = payload.get("error", "未知错误")
            text = f"❌ #{task_id} {task_name} 失败\n原因: {error}"
        else:
            return  # 中间状态不推送

        # 查找绑定的微信 openid
        # 从 payload 中提取 user_id，若没有则跳过
        user_id = payload.get("user_id")
        if not user_id:
            return

        openid = get_openid_for_user(user_id)
        if not openid:
            return

        outbound_queue.enqueue(OutboundMessage(
            openid=openid,
            content=text,
            priority="normal",
        ))

    event_bus.subscribe("task:update", on_task_update)
    logger.info("wechat_subscribers_registered")
