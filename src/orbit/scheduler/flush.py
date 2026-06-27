"""Pre-compaction Memory Flush (Phase 2 AC11a).

对标 OpenClaw memory flush:
  检测静默 turn（assistant 无 tool_calls + 无实质性内容）
  → 自动写 daily log 到 MEMORY.md
  → 发送 NO_REPLY 事件（驾驶舱不可见）
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from orbit.memory.models import MemoryFileType
from orbit.memory.store import MemoryStore

logger = structlog.get_logger("orbit.scheduler.flush")

# 静默短语——这些回复视为"无实质内容"
SILENT_PHRASES = {
    "好的",
    "ok",
    "ok.",
    "继续",
    "明白",
    "understood",
    "收到",
    "got it",
    "i see",
    "",
    "思考中",
    "让我想想",
    "let me think",
    "正在处理",
}


def is_silent_turn(messages: list[dict[str, Any]]) -> bool:
    """检测当前轮次是否为静默 turn.

    静默 turn 条件:
    1. 最后一条 assistant 消息没有 tool_calls
    2. 内容为空或是纯确认性短语
    """
    if not messages:
        return False

    # 找最后一条 assistant 消息
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        if msg.get("tool_calls"):
            return False  # 有工具调用 → 不是静默
        content = str(msg.get("content", "")).strip().lower()
        # 空或纯确认
        return not content or content in SILENT_PHRASES or len(content) < 20

    return False


def build_daily_log_entry(
    turn: int,
    task_id: str,
    agent_name: str,
    messages: list[dict[str, Any]],
) -> str:
    """构建每日日志条目——追加到 MEMORY.md."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    date = now[:10]

    # 提取上下文摘要
    context_lines: list[str] = []
    for msg in messages[-5:]:
        role = msg.get("role", "?")
        content = str(msg.get("content", ""))[:100]
        if content.strip():
            context_lines.append(f"  [{role}] {content}")

    context_snapshot = "\n".join(context_lines) if context_lines else "无上下文"

    return (
        f"## Session {date} — Silent Turn {turn}\n\n"
        f"- **时间**: {now}\n"
        f"- **Agent**: {agent_name}\n"
        f"- **Task**: {task_id}\n\n"
        f"**上下文快照**:\n{context_snapshot}\n"
    )


class MemoryFlushHandler:
    """Pre-compaction memory flush 处理器.

    集成到 ReActAgent 循环中——静默 turn 时自动刷新记忆。
    """

    def __init__(self, memory_store: MemoryStore | None = None) -> None:
        self._store = memory_store or MemoryStore()
        self._flush_count = 0

    async def maybe_flush(
        self,
        turn: int,
        task_id: str,
        agent_name: str,
        messages: list[dict[str, Any]],
    ) -> bool:
        """检查并执行记忆刷新.

        Returns:
            True 如果发生了刷新
        """
        if not is_silent_turn(messages):
            return False

        entry = build_daily_log_entry(turn, task_id, agent_name, messages)
        self._store.append_to_file(MemoryFileType.EPISODIC, entry)
        self._flush_count += 1

        logger.info(
            "memory_flushed",
            turn=turn,
            agent=agent_name,
            total_flushes=self._flush_count,
        )
        return True

    @property
    def flush_count(self) -> int:
        return self._flush_count
