"""CancellationToken——轻量取消令牌。

对标 OpenClaw wrapToolWithAbortSignal: 传播取消信号,
cleanup 总是执行（对标 Effect.uninterruptible）。

WHY asyncio.Event 而非 threading.Event:
  调度器和 Agent 都在 asyncio 事件循环中运行，
  asyncio.Event 无阻塞、无需线程同步。
"""

from __future__ import annotations

import asyncio


class CancellationToken:
    """轻量取消令牌。

    用法:
        token = CancellationToken()
        # ... 在 Agent 循环中 ...
        if await token.is_cancelled:
            yield StreamEvent(type=StreamEventType.CANCELLED, ...)
            break

    从外部取消:
        token.cancel()
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._event = asyncio.Event()

    def cancel(self) -> None:
        """发出取消信号。幂等——多次调用安全。"""
        self._cancelled = True
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """同步检查是否已取消。用于快速路径——不阻塞。"""
        return self._cancelled

    async def wait_if_cancelled(self, timeout: float = 0.0) -> bool:
        """等待取消信号。timeout=0 表示立即检查不等待。

        Returns:
            True 如果已取消。
        """
        if self._cancelled:
            return True
        if timeout > 0:
            try:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            except TimeoutError:
                return False
        return self._cancelled
