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

import re
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


# 摘要 prompt——保留关键信息（代码任务用）
SUMMARY_PROMPT_CODE = (
    "将以下 Agent 对话历史压缩为一段结构化摘要。保留：\n"
    "1. 已做出的决策和理由\n"
    "2. 修改的文件名和行号\n"
    "3. 约束条件——硬性限制（不能碰的文件、不能改的接口）\n"
    "4. 当前进度——完成了什么、卡在哪里\n"
    "5. 下一步——接下来要做什么\n"
    "6. 错误及修复方案\n"
    "压缩后不超过 500 字符。\n\n"
    "对话历史：\n{conversation}"
)

# 对话场景摘要 prompt（Chatter/Clarifier 用）
SUMMARY_PROMPT_CHAT = (
    "将以下对话历史压缩为一段结构化摘要。保留：\n"
    "1. 用户偏好和习惯（技术栈、编码风格、沟通偏好）\n"
    "2. 关键决策和选择理由\n"
    "3. 引用的文件路径和项目上下文\n"
    "4. 约束条件——用户明确的限制和要求\n"
    "5. 当前进度——已完成、待处理、阻塞项\n"
    "6. 待确认的问题和未解决的模糊点\n"
    "压缩后不超过 500 字符。\n\n"
    "对话历史：\n{conversation}"
)

# V16.0 Phase B: 压缩后自动恢复
COMPACT_RESUME_PROMPT = "以上是对话历史的压缩摘要。请基于摘要继续回答用户的问题。"

# 向后兼容别名
SUMMARY_PROMPT = SUMMARY_PROMPT_CODE


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
        agent_role: str = "",  # 用于选择对话/代码 prompt
    ) -> list[dict[str, Any]]:
        """使用廉价 LLM 摘要旧轮次——仅保留最后 N 轮完整。

        WHY 保留最后 3 轮: LLM 需要最近的上下文才能连贯思考。
        agent_role ∈ {chatter, clarifier} → 对话 prompt；其他 → 代码 prompt。
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
        # P1 SEC-8/P2-2: 脱敏 API key/密码/私钥 (IGNORECASE+PEM 完整块)
        _SENSITIVE = re.compile(
            r'(sk-[A-Za-z0-9_-]{10,})'
            r'|(Bearer\s+[A-Za-z0-9._\-=]+)'
            r'|(api_?key\s*[:=]\s*["\']?\S+["\']?)'
            r'|(password\s*[:=]\s*["\']?\S+["\']?)'
            r'|(-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----.*?-----END\s+\w+\s+PRIVATE\s+KEY-----)',
            re.IGNORECASE | re.DOTALL,
        )
        conversation_text = "\n".join(
            _SENSITIVE.sub(
                '***REDACTED***',
                f"[{m.get('role','?')}] {str(m.get('content',''))[:300]}",
            )
            for m in old_messages
            if m.get("content")
        )
        # 场景自动识别：Chatter/Clarifier → 对话 prompt；其他 → 代码 prompt
        is_chat = agent_role.lower() in ("chatter", "clarifier")
        prompt_template = SUMMARY_PROMPT_CHAT if is_chat else SUMMARY_PROMPT_CODE
        summary_prompt = prompt_template.format(conversation=conversation_text)

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
        Phase 3: 通过 SessionRegistry 持久化子 session + messages cold storage。
        """
        import json as _json
        import os as _os
        import uuid

        child_id = str(uuid.uuid4())[:8]
        # 尝试写入 SessionRegistry 获取真实 session_id
        try:
            from orbit.sessions.registry import SessionRegistry

            registry = SessionRegistry()
            child_id = registry.create_fork(task_id, reason=f"context_overflow_turn_{turn}")
            logger.info("session_fork_persisted", child_id=child_id[:8], parent=task_id[:8])
        except Exception as e:
            logger.warning("session_fork_fallback_uuid", error=str(e))

        # 压缩后的 messages 序列化到 cold storage（.orbit/sessions/ 目录）
        try:
            cold_dir = _os.path.join(".orbit", "sessions")
            _os.makedirs(cold_dir, exist_ok=True)
            cold_path = _os.path.join(cold_dir, f"{child_id}_{turn}.json")
            with open(cold_path, "w", encoding="utf-8") as f:
                _json.dump(messages, f, ensure_ascii=False, indent=2)
            logger.info("session_cold_storage_saved", path=cold_path, messages=len(messages))
        except Exception as e:
            logger.warning("session_cold_storage_failed", error=str(e))

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
