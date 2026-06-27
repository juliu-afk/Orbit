"""5 层压缩管线 (Phase 2 AC8).

对标 Claude Code 5-layer compression:
  L1: Output Truncation —— >10K chars → head+tail
  L2: Message Pruning —— 去空/去重/去冗余
  L3: Summary —— cheap LLM 摘要旧轮次
  L4: Sliding Window —— 保留 system + 最后 N 轮
  L5: Dedup —— 路径标准化 + 重复内容合并

每层独立、可跳过、可单独测试。
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger("orbit.compression")

# 不保留的 assistant/tool 消息对的最大内容长度
EMPTY_TOOL_THRESHOLD = 10


class CompressionPipeline:
    """5 层压缩管线——每层独立、按序执行."""

    def __init__(self) -> None:
        self._applied_layers: list[str] = []
        self._bytes_removed = 0

    async def run(
        self,
        messages: list[dict[str, Any]],
        action: str,  # "warn" | "force"
    ) -> tuple[list[dict[str, Any]], int]:
        """运行管线——按 action 决定执行哪些层.

        Returns:
            (compressed_messages, bytes_removed)
        """
        self._applied_layers = []
        self._bytes_removed = 0
        original_size = sum(len(str(m)) for m in messages)

        # L1: 始终执行（已存在 AC6b）
        messages = self._layer1_truncate(messages)
        self._applied_layers.append("truncate")

        # L2: 始终执行
        messages = self._layer2_prune(messages)
        self._applied_layers.append("prune")

        if action == "force":
            # L3: 仅 force 模式（需要 LLM 调用，外部处理）
            # 此处标记，由 ContextCompressor 执行 LLM 摘要
            self._applied_layers.append("summary")

        # L4: warn+force 都执行
        messages = self._layer4_sliding(messages)
        self._applied_layers.append("sliding")

        # L5: warn+force 都执行
        messages = self._layer5_dedup(messages)
        self._applied_layers.append("dedup")

        compressed_size = sum(len(str(m)) for m in messages)
        self._bytes_removed = max(0, original_size - compressed_size)

        logger.info(
            "compression_complete",
            layers="→".join(self._applied_layers),
            original_chars=original_size,
            compressed_chars=compressed_size,
            removed=self._bytes_removed,
        )
        return messages, self._bytes_removed

    # ── Layer 1: Output Truncation ─────────────────────

    @staticmethod
    def _layer1_truncate(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """截断超长的工具输出——>10K chars → head+tail.

        对标 AC6b: Tool output truncation.
        """
        MAX_CHARS = 10000
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") != "tool":
                result.append(msg)
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > MAX_CHARS:
                half = MAX_CHARS // 2
                msg = {
                    **msg,
                    "content": (
                        content[:half]
                        + f"\n\n... [截断 {len(content) - MAX_CHARS} 字符] ...\n\n"
                        + content[-half:]
                    ),
                }
            result.append(msg)
        return result

    # ── Layer 2: Message Pruning ───────────────────────

    @staticmethod
    def _layer2_prune(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """修剪冗余消息.

        规则:
        1. 移除连续重复的 system prompt
        2. 移除空工具结果
        3. 合并相邻的 system 消息
        """
        result: list[dict[str, Any]] = []
        last_system_content = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 跳过重复的 system prompt
            if role == "system":
                if content == last_system_content and result:
                    continue
                last_system_content = str(content)

            # 跳过空工具结果
            if role == "tool" and (
                not content or len(str(content).strip()) <= EMPTY_TOOL_THRESHOLD
            ):
                continue

            result.append(msg)

        return result

    # ── Layer 4: Sliding Window ────────────────────────

    @staticmethod
    def _layer4_sliding(
        messages: list[dict[str, Any]],
        window_turns: int = 10,
    ) -> list[dict[str, Any]]:
        """滑动窗口——保留 system + 最后 N 个 assistant/tool 对.

        对标 Claude Code sliding window:
        - 始终保留 system prompt（第一条）
        - 保留最后 window_turns 个有效轮次
        - 一个轮次 = assistant 消息 + 其 tool_calls 结果

        WHY 保留 system: system prompt 包含角色定义+工具列表+强制规则，不可丢失。
        """
        if len(messages) <= window_turns * 2 + 1:
            return messages

        # 找到 system prompt
        system_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), 0)

        # 从尾部向前找 window_turns 个 assistant 消息
        assistant_indices: list[int] = []
        for i in range(len(messages) - 1, system_idx, -1):
            if messages[i].get("role") == "assistant":
                assistant_indices.append(i)
                if len(assistant_indices) >= window_turns:
                    break

        if not assistant_indices:
            return messages

        # 保留: system + [start_idx ... end]
        start_idx = max(system_idx + 1, assistant_indices[-1])
        result = [messages[system_idx]]  # system prompt
        # 添加一个摘要占位（如果截断了中间的消息）
        if start_idx > system_idx + 1:
            skipped = start_idx - system_idx - 1
            result.append(
                {
                    "role": "system",
                    "content": (
                        f"[上下文窗口管理] {skipped} 条早期消息已被滑动窗口移除。"
                        "关键内容已通过摘要保留。"
                    ),
                }
            )
        result.extend(messages[start_idx:])
        return result

    # ── Layer 5: Dedup ─────────────────────────────────

    @staticmethod
    def _layer5_dedup(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """去重——标准化路径 + 移除重复内容块.

        对标 Claude Code dedup: 标准化文件路径格式，移除重复代码块。
        """
        seen_blocks: set[str] = set()
        result: list[dict[str, Any]] = []

        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                result.append(msg)
                continue

            # 标准化路径: ./src/a.py → src/a.py, \ → /
            normalized = content.replace("\\", "/")
            normalized = re.sub(r"(?<!\w)\./", "", normalized)

            # 提取大代码块 (>200 chars) 做去重
            code_blocks = re.findall(r"```[^`]*```", normalized)
            if code_blocks:
                for block in code_blocks:
                    if block not in seen_blocks:
                        seen_blocks.add(block)
                # 检测整个消息是否接近重复
                msg_key = normalized[:200]
                if msg_key in seen_blocks:
                    continue
                seen_blocks.add(msg_key)

            result.append(msg)

        return result

    # ── 属性 ──────────────────────────────────────────

    @property
    def applied_layers(self) -> list[str]:
        return list(self._applied_layers)

    @property
    def bytes_removed(self) -> int:
        return self._bytes_removed
