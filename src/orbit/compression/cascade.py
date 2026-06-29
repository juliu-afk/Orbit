"""级联上下文裁剪——在 5 层压缩管线之前运行，减少 LLM 摘要的需求。

对标 SWE-Pruner 分级: mechanical before semantic before LLM。

执行顺序（破坏性递增）:
Stage 1: 剥离已消费的大型工具输出（低破坏性）
Stage 2: 移除无状态变更的中间推理（中破坏性）
Stage 3: 结构化摘要旧轮次——但 Ledger 层永不被压缩（高破坏性）
Stage 4: LLM 全量摘要（最高破坏性——仅当 Stage 1-3 不足时）

v4 定位: 单 Task 会话的安全网。
单 Task 通常不触发（≤20 turns，独立 128K），
但复杂子任务工具调用密集时仍可能接近 128K——作为安全网保留。

WHY 级联而非一次性: 每一层破坏性递增——
能用低破坏性解决的就不触发高破坏性。
"""

from __future__ import annotations

import structlog
from typing import Any

from orbit.compression.models import CompressionAction

logger = structlog.get_logger("orbit.compression")

# P2-2: 阈值通过 __init__ 可配置
DEFAULT_LARGE_OUTPUT_THRESHOLD = 5000
DEFAULT_CONSUMED_OUTPUT_MAX_TURNS = 3
DEFAULT_INEFFECTUAL_MIN_CHARS = 100

# 保留旧名以兼容其他模块引用
LARGE_OUTPUT_THRESHOLD = DEFAULT_LARGE_OUTPUT_THRESHOLD
CONSUMED_OUTPUT_MAX_TURNS = DEFAULT_CONSUMED_OUTPUT_MAX_TURNS
INEFFECTUAL_MIN_CHARS = DEFAULT_INEFFECTUAL_MIN_CHARS


class CascadePruner:
    """级联上下文裁剪器。

    在 ContextCompressor 的 5 层管线之前运行。
    逐级增加破坏性——每级后检查预算是否已满足。

    Usage:
        pruner = CascadePruner(memory=None, large_output_threshold=5000)
        messages, memory = await pruner.prune(messages, memory, budget)
    """

    def __init__(
        self,
        memory: Any = None,
        large_output_threshold: int = DEFAULT_LARGE_OUTPUT_THRESHOLD,
        consumed_output_max_turns: int = DEFAULT_CONSUMED_OUTPUT_MAX_TURNS,
        ineffectual_min_chars: int = DEFAULT_INEFFECTUAL_MIN_CHARS,
    ) -> None:
        self._memory = memory
        self._large_threshold = large_output_threshold
        self._consumed_turns = consumed_output_max_turns
        self._ineffectual_min = ineffectual_min_chars
        self._stages_applied: list[str] = []
        self._bytes_removed_total: int = 0

    async def prune_if_needed(
        self,
        messages: list[dict[str, Any]],
        memory: Any = None,
        budget: Any = None,  # TokenBudgetTracker
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        """级联裁剪——仅在预算紧张时触发。

        Args:
            messages: 当前消息列表
            memory: ThreeTierMemory 实例
            budget: TokenBudgetTracker 实例

        Returns:
            (pruned_messages, stages_applied, bytes_removed)
        """
        if budget is None:
            return messages, [], 0

        mem = memory or self._memory
        self._stages_applied = []
        self._bytes_removed_total = 0
        original_size = sum(len(str(m)) for m in messages)

        # 只在 FORCE 模式时触发——上下文充足时 no-op
        if budget.check_threshold() != CompressionAction.FORCE:
            return messages, [], 0

        current = list(messages)

        # Stage 1: 剥离已消费的大型工具输出
        current = self._stage1_strip_consumed(current, mem)
        self._stages_applied.append("strip_consumed")
        if budget.check_threshold() != CompressionAction.FORCE:
            return self._finish(current, original_size)

        # Stage 2: 移除无状态变更的推理
        current = self._stage2_remove_effectless(current, mem)
        self._stages_applied.append("remove_ineffectual")
        if budget.check_threshold() != CompressionAction.FORCE:
            return self._finish(current, original_size)

        # Stage 3: 结构化摘要旧轮次——Ledger 层不被压缩
        current = self._stage3_structured_summary(current, mem)
        self._stages_applied.append("structured_summary")
        if budget.check_threshold() != CompressionAction.FORCE:
            return self._finish(current, original_size)

        # Stage 4: 标记需要 LLM 摘要（由 ContextCompressor 执行）
        self._stages_applied.append("need_llm_summary")

        return self._finish(current, original_size)

    # ── Stage 1: 剥离已消费输出 ─────────────────────────

    def _stage1_strip_consumed(
        self,
        messages: list[dict[str, Any]],
        memory: Any,
    ) -> list[dict[str, Any]]:
        """剥离已消费的大型工具输出。

        保留: 错误信息、验证失败输出、最近 N 轮输出
        剥离: 成功读取的长文件内容、已通过的测试输出

        WHY: 工具输出占上下文最大比例——Agent 读完文件并做出决策后，
        原始文件内容不再需要。"已消费" = 后续 assistant 消息引用了此输出。
        """
        result: list[dict[str, Any]] = []

        for i, msg in enumerate(messages):
            if msg.get("role") != "tool":
                result.append(msg)
                continue

            content = msg.get("content", "")
            if not isinstance(content, str):
                result.append(msg)
                continue

            # 小型输出——不处理
            if len(content) < self._large_threshold:
                result.append(msg)
                continue

            # 错误/失败——始终保留
            if self._is_error_output(content):
                result.append(msg)
                continue

            # 检查是否已被消费——后续 assistant 中引用了此输出的内容
            consumed = self._is_consumed(msg, messages, i)
            if consumed:
                # 替换为摘要占位
                result.append({
                    **{k: v for k, v in msg.items() if k != "content"},
                    "content": (
                        f"[上下文裁剪] {len(content)} 字符的工具输出已被消费并移除。"
                        f"关键内容: {content[:200]}..."
                    ),
                })
                logger.debug(
                    "cascade_stage1_stripped",
                    chars=len(content),
                    tool_call_id=msg.get("tool_call_id", ""),
                )
            else:
                result.append(msg)

        return result

    # ── Stage 2: 移除无效果推理 ─────────────────────────

    def _stage2_remove_effectless(
        self,
        messages: list[dict[str, Any]],
        memory: Any,
    ) -> list[dict[str, Any]]:
        """移除无状态变更的推理——思考但没产生任何代码变更或决策的轮次。

        保留: 产生了文件变更或架构决策的推理
        移除: 纯探索性推理（"让我看看..."但没改任何东西）
        失败方法记录到 memory.failed_approaches（不再重复）
        """
        result: list[dict[str, Any]] = []
        # 跟踪最近的 assistant→tool 对是否有实际效果
        consecutive_ineffectual = 0
        max_ineffectual = 3

        for i, msg in enumerate(messages):
            role = msg.get("role", "")

            if role == "assistant":
                content = msg.get("content", "")
                has_tool_calls = bool(msg.get("tool_calls"))

                # 无 tool_calls + 内容短 → 可能是无效果推理
                if not has_tool_calls and isinstance(content, str):
                    if len(content) < self._ineffectual_min:
                        consecutive_ineffectual += 1
                        if consecutive_ineffectual > max_ineffectual:
                            # 记录到失败方法
                            if memory and hasattr(memory, 'record_failure'):
                                memory.record_failure(f"无效果推理: {content[:100]}")
                            continue  # 跳过此消息
                    else:
                        consecutive_ineffectual = 0
                elif has_tool_calls:
                    consecutive_ineffectual = 0
                result.append(msg)

            elif role == "tool":
                # 如果上一 assistant 被移除，对应的 tool 结果也移除
                if consecutive_ineffectual > max_ineffectual + 1:
                    continue
                result.append(msg)
                consecutive_ineffectual = 0
            else:
                result.append(msg)

        return result

    # ── Stage 3: 结构化摘要旧轮次 ────────────────────────

    def _stage3_structured_summary(
        self,
        messages: list[dict[str, Any]],
        memory: Any,
    ) -> list[dict[str, Any]]:
        """结构化摘要旧轮次——用 memory.to_progress_injection() 替代旧消息。

        Ledger 层（目标/约束/架构决策）始终保留在 system prompt 前部——永不被压缩。
        旧消息替换为结构化进度摘要。
        """
        if not memory or not hasattr(memory, 'to_progress_injection'):
            return messages

        # 保留 system prompt + 最后 5 轮
        KEEP_LAST_TURNS = 5
        system_msg = None
        for i, m in enumerate(messages):
            if m.get("role") == "system":
                system_msg = m
                break

        # 从尾部计数 assistant 消息
        assistant_indices: list[int] = []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                assistant_indices.append(i)
                if len(assistant_indices) >= KEEP_LAST_TURNS:
                    break

        if not assistant_indices:
            return messages

        tail_start = assistant_indices[-1]
        head_messages = messages[:tail_start]
        tail_messages = messages[tail_start:]

        # 如果头部只有 system + 少量消息——不值得压缩
        if len(head_messages) <= 2:
            return messages

        # 构建压缩后的消息列表
        result: list[dict[str, Any]] = []

        # Ledger 层保护——system prompt 永不被移除
        if system_msg:
            result.append(system_msg)

        # 注入结构化进度摘要——替代被移除的旧消息
        progress_text = memory.to_progress_injection()
        skipped = len(head_messages) - (1 if system_msg else 0)
        result.append({
            "role": "system",
            "content": (
                f"[结构化进度恢复] {skipped} 条早期消息已被级联裁剪。\n"
                "以下为压缩前的结构化进度——请基于此继续，不重复已完成任务。\n\n"
                f"{progress_text}"
            ),
        })

        # 保留尾部消息（最近 N 轮）
        result.extend(tail_messages)

        logger.info(
            "cascade_stage3_structured_summary",
            removed=skipped,
            kept=len(tail_messages),
        )
        return result

    # ── Stage 4: 标记 LLM 摘要需求 ──────────────────────

    # Stage 4 由 ContextCompressor 执行——此处只标记需要 LLM 摘要。
    # 5 层管线中的 L3 Summary 会处理。

    # ── 辅助方法 ────────────────────────────────────────

    @staticmethod
    def _is_error_output(content: str) -> bool:
        """检测是否为错误输出——始终保留。"""
        error_markers = [
            "Traceback", "Error:", "FAILED", "FAIL:", "error:",
            "Exception:", "assert", "Fatal:", "panic:",
            "失败", "错误", "异常",
        ]
        content_head = content[:500].lower()
        return any(m.lower() in content_head for m in error_markers)

    @staticmethod
    def _is_consumed(
        tool_msg: dict[str, Any],
        messages: list[dict[str, Any]],
        tool_index: int,
    ) -> bool:
        """检查工具输出是否已被后续 assistant 消息引用/消费。

        "已消费" = 后续 assistant 消息中引用了此输出的内容。
        """
        tool_content = tool_msg.get("content", "")
        if not isinstance(tool_content, str) or not tool_content:
            return False

        # 只在最近 self._consumed_turns 轮后的 assistant 中检查
        tool_id = tool_msg.get("tool_call_id", "")
        for j in range(tool_index + 1, min(tool_index + 1 + self._consumed_turns * 2, len(messages))):
            msg = messages[j]
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 30:
                    # 简单启发式——assistant 有实质性内容 = 工具输出已被消费
                    return True
                if msg.get("tool_calls"):
                    # 有后续 tool_calls = 在处理中——暂不剥离
                    return False

        # 超过 N 轮没有 assistant 消费——可以剥离
        return True

    def _finish(
        self,
        messages: list[dict[str, Any]],
        original_size: int,
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        """计算最终指标并返回。"""
        compressed_size = sum(len(str(m)) for m in messages)
        self._bytes_removed_total = max(0, original_size - compressed_size)
        logger.info(
            "cascade_prune_complete",
            stages="→".join(self._stages_applied),
            original_chars=original_size,
            compressed_chars=compressed_size,
            removed=self._bytes_removed_total,
        )
        return messages, self._stages_applied, self._bytes_removed_total

    @property
    def stages_applied(self) -> list[str]:
        return list(self._stages_applied)

    @property
    def bytes_removed(self) -> int:
        return self._bytes_removed_total
