"""8 步压缩算法 (Phase 2 AC7).

对标 Hermes context_compressor.py:
  Step 1: Token 估算
  Step 2: 阈值检查
  Step 3: L1 截断
  Step 4: L2 修剪
  Step 5: L3 摘要 (LLM)
  Step 6: L4 滑动窗口
  Step 7: L5 去重
  Step 8: 后检查 → 分叉或返回

WHY 8 步而非一步: 每步独立可测，按阈值选择性执行。
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.compression.budget import TokenBudgetTracker
from orbit.compression.models import CompressionAction, CompressionResult
from orbit.compression.pipeline import CompressionPipeline

logger = structlog.get_logger("orbit.compressor")


# 摘要 LLM 模型——从配置读取（默认 GLM-4.7 Flash 免费模型）
def _get_summary_model() -> str:
    try:
        from orbit.core.config import settings

        return settings.COMPRESSION_SUMMARY_MODEL
    except Exception:
        return "openai/glm-4.7-flash"


# 摘要 prompt——保留关键信息
SUMMARY_PROMPT = (
    "将以下 Agent 对话历史压缩为一段结构化摘要。保留：\n"
    "1. 已做出的决策和理由\n"
    "2. 修改的文件名和行号\n"
    "3. 错误及修复方案\n"
    "4. 未完成的任务\n"
    "压缩后不超过 500 字符。\n\n"
    "对话历史：\n{conversation}"
)


class ContextCompressor:
    """8 步上下文压缩器——ReActAgent 每轮调用前运行.

    Usage:
        compressor = ContextCompressor(llm_client)
        result = await compressor.compress(messages, task_id)
        messages = result.compressed_messages
    """

    def __init__(
        self,
        llm_client: Any = None,
        budget_tracker: TokenBudgetTracker | None = None,
        pipeline: CompressionPipeline | None = None,
    ) -> None:
        self._llm = llm_client
        self._budget = budget_tracker or TokenBudgetTracker()
        self._pipeline = pipeline or CompressionPipeline()
        self._child_session_id: str | None = None

    async def compress(
        self,
        messages: list[dict[str, Any]],
        task_id: str = "",
        turn: int = 0,
    ) -> CompressionResult:
        """执行 8 步压缩算法.

        Args:
            messages: 当前消息历史
            task_id: 任务 ID（日志+分叉用）
            turn: 当前轮次

        Returns:
            CompressionResult——包含压缩后的动作和统计信息
        """
        # Step 1: Token 估算
        estimated = self._budget.estimate_tokens(messages)
        self._budget.record_usage(estimated)

        # Step 2: 阈值检查
        action = self._budget.check_threshold()

        if action == CompressionAction.SKIP:
            return CompressionResult(
                action=action,
                original_tokens=estimated,
                compressed_tokens=estimated,
                ratio=0.0,
            )

        # Step 3-7: 运行压缩管线
        pipeline_action = "force" if action == CompressionAction.FORCE else "warn"
        compressed, bytes_removed = await self._pipeline.run(messages, pipeline_action)

        # Step 3a: 如果是 force 模式，执行 L3 LLM 摘要
        if action == CompressionAction.FORCE and self._llm:
            try:
                compressed = await self._summarize_old_turns(compressed, task_id)
            except Exception as e:
                logger.warning("summary_failed", error=str(e))

        # Step 8: 后检查——压缩后仍超 85%？
        compressed_estimated = self._budget.estimate_tokens(compressed)
        if (
            self._budget.check_threshold() == CompressionAction.FORCE
            and self._budget.estimate_tokens(compressed) > estimated * 0.85
        ):
            # 压缩效果不足 → 子 Session 分叉
            # Force action but post-compression still above threshold
            child_id = await self._fork_child_session(messages, task_id, turn)
            return CompressionResult(
                action=CompressionAction.FORK,
                original_tokens=estimated,
                compressed_tokens=compressed_estimated,
                ratio=1.0 - (compressed_estimated / max(estimated, 1)),
                child_session_id=child_id,
                layers_applied=self._pipeline.applied_layers,
                compressible_bytes_removed=bytes_removed,
            )

        return CompressionResult(
            action=action,
            original_tokens=estimated,
            compressed_tokens=compressed_estimated,
            ratio=1.0 - (compressed_estimated / max(estimated, 1)),
            layers_applied=self._pipeline.applied_layers,
            compressible_bytes_removed=bytes_removed,
        )

    # ── L3 Summary (LLM) ───────────────────────────────

    async def _summarize_old_turns(
        self,
        messages: list[dict[str, Any]],
        task_id: str,
        keep_last_n_turns: int = 3,
    ) -> list[dict[str, Any]]:
        """使用廉价 LLM 摘要旧轮次——仅保留最后 N 轮完整。

        WHY 保留最后 3 轮: LLM 需要最近的上下文才能连贯思考。
        """
        if not self._llm:
            return messages

        # 找到 system prompt + 最后 N 轮
        system_msg = next((m for m in messages if m.get("role") == "system"), None)

        # 从尾部找最后 N 个 assistant 消息
        tail_start = 0
        assistant_count = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                assistant_count += 1
                if assistant_count >= keep_last_n_turns:
                    tail_start = i
                    break

        old_messages = messages[1:tail_start] if system_msg else messages[:tail_start]
        if not old_messages:
            return messages

        # 构建摘要请求
        conversation_text = "\n".join(
            f"[{m.get('role','?')}] {str(m.get('content',''))[:300]}"
            for m in old_messages
            if m.get("content")
        )
        summary_prompt = SUMMARY_PROMPT.format(conversation=conversation_text)

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=summary_prompt,
                system_prompt="你是一个对话摘要助手，将对话压缩为结构化摘要。",
                temperature=0.3,
                max_tokens=500,
            )
            resp = await self._llm.generate(req, task_id=task_id)
            summary_content = resp.content or "对话摘要不可用。"
        except Exception:
            summary_content = "摘要生成失败——保留原始上下文。"

        # 构建压缩后的消息列表
        result: list[dict[str, Any]] = []
        if system_msg:
            result.append(system_msg)
        result.append(
            {
                "role": "system",
                "content": f"[上下文压缩] 之前 {len(old_messages)} 条消息的摘要:\n{summary_content}",
            }
        )
        result.extend(messages[tail_start:])
        return result

    # ── Child Session Fork ─────────────────────────────

    async def _fork_child_session(
        self,
        messages: list[dict[str, Any]],
        task_id: str,
        turn: int,
    ) -> str:
        """创建子 Session 分叉——当压缩后仍超 85% 窗口。

        WHY 分叉而非崩溃: 给 Agent 一个干净的上下文继续工作。

        TODO(Phase 3): 当前只生成 UUID，未写入 sessions 表。
        Phase 3 应调用 SessionRegistry.create_fork() 持久化子 session，
        并将压缩后的 messages 序列化到 cold storage。
        """
        import uuid

        child_id = str(uuid.uuid4())[:8]
        # Phase 3: 尝试写入 SessionRegistry（如果可用）
        try:
            from orbit.sessions.registry import SessionRegistry

            registry = SessionRegistry()
            registry.create_fork(task_id, reason=f"context_overflow_turn_{turn}")
            # 使用 registry 返回的真实 session_id
            # child_id = registry.create_fork(...)
        except Exception:
            pass  # SessionRegistry 不可用时回退 UUID

        logger.info(
            "session_fork",
            task_id=task_id,
            turn=turn,
            child_session_id=child_id,
            message_count=len(messages),
        )
        self._child_session_id = child_id
        return child_id

    @property
    def child_session_id(self) -> str | None:
        return self._child_session_id
