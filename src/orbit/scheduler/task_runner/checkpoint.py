"""TaskRunner 检查点 Mixin——_continue_from + _save_checkpoint + 事件发布。

从 task_runner.py 拆分。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from orbit.api.schemas.task import TaskState
from orbit.checkpoint.manager import CheckpointData
from orbit.events.schemas import DashboardEvent, TaskUpdatePayload, TokenUpdatePayload

logger = structlog.get_logger("orbit.scheduler.runner")

TERMINAL_STATES = {TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED}

STATE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.SCOPING,
    TaskState.SCOPING: TaskState.PLANNING,
    TaskState.PLANNING: TaskState.CODING,
    TaskState.CODING: TaskState.VERIFYING,
    TaskState.VERIFYING: TaskState.DONE,
}

FAST_LANE_TRANSITIONS: dict[TaskState, TaskState] = {
    TaskState.IDLE: TaskState.PARSING,
    TaskState.PARSING: TaskState.CODING,
    TaskState.CODING: TaskState.DONE,
    TaskState.DONE: TaskState.DONE,
}


class InvalidStateTransitionError(Exception):
    """非法状态转换."""


def _transition(current: TaskState, fast_lane: bool = False) -> TaskState:
    """执行状态转换（纯函数）。"""
    if current in TERMINAL_STATES:
        raise InvalidStateTransitionError(f"终态 {current.value} 不可转换")
    transitions = FAST_LANE_TRANSITIONS if fast_lane else STATE_TRANSITIONS
    if current not in transitions:
        raise InvalidStateTransitionError(f"状态 {current.value} 无后继")
    return transitions[current]


def _state_to_progress(state: TaskState) -> float:
    """状态→进度比例（0.0-1.0，匹配 CheckpointData.progress 约束）。"""
    progress_map = {
        TaskState.IDLE: 0.0,
        TaskState.PARSING: 0.10,
        TaskState.SCOPING: 0.20,
        TaskState.PLANNING: 0.30,
        TaskState.CODING: 0.60,
        TaskState.VERIFYING: 0.85,
        TaskState.DONE: 1.0,
        TaskState.FAILED: 1.0,
        TaskState.CANCELLED: 1.0,
    }
    return progress_map.get(state, 0.0)


class TaskCheckpointMixin:
    async def _continue_from(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> TaskState:
        """从指定状态继续执行."""
        current = state
        while current not in TERMINAL_STATES:
            try:
                observation = await self._agent_cycle(task_id, current, context)
                context.setdefault("artifacts", {})[current.value] = observation
                current = _transition(current, self._fast_lane)
                await self._save_checkpoint(task_id, current, context)
            except asyncio.CancelledError:
                raise  # P0-1: 不吞取消信号
            except Exception as e:
                logger.error("resume_failed", task_id=task_id, error=str(e))
                current = TaskState.FAILED
                await self._save_checkpoint(task_id, current, {**context, "error": str(e)})
                return current
        return current

    # ── 检查点 + 事件 ──────────────────────────────────

    async def _save_checkpoint(
        self, task_id: str, state: TaskState, context: dict[str, Any]
    ) -> None:
        """保存检查点."""
        if self.checkpoint is None:
            return
        data = CheckpointData(  # type: ignore[call-arg]
            task_id=task_id,
            state=state.value,
            progress=_state_to_progress(state),
            context=context,
        )
        await self.checkpoint.save(task_id, data)

    def _publish_task_update(
        self,
        task_id: str,
        state: str,
        progress: float,
        dag: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """发布 task:update 事件."""
        if self._event_bus is None:
            return
        output: str | None = None
        if state in ("CODING", "DONE") and context:
            artifacts = context.get("artifacts", {})
            output = artifacts.get("CODING")
        self._event_bus.publish(
            DashboardEvent(
                type="task:update",
                task_id=task_id,
                payload=TaskUpdatePayload(
                    task_id=task_id,
                    state=state,
                    progress=progress,
                    dag=dag or [],
                    timestamp=datetime.now(UTC).isoformat(),
                    output=output,
                ).model_dump(),
            )
        )

    def _publish_token_update(
        self, task_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int
    ) -> None:
        """发布 token:update 事件."""
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DashboardEvent(
                type="token:update",
                task_id=task_id,
                payload=TokenUpdatePayload(
                    task_id=task_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    timestamp=datetime.now(UTC).isoformat(),
                ).model_dump(),
            )
        )

    @staticmethod
    def _extract_keywords(prd_text: str) -> list[str]:
        """从 PRD 文本提取技术关键词——减熵闭环-1.

        简单分词 + 停用词过滤 + 标识符保留。零外部依赖。
        供 B1(上下文裁剪)/B3(模板库)/B5(决策日志) 使用。
        """
        if not prd_text:
            return []

        # 中文停用词——高频虚词
        _stop = {
            "的",
            "是",
            "在",
            "和",
            "了",
            "有",
            "不",
            "我",
            "我们",
            "要",
            "可以",
            "这个",
            "那个",
            "一个",
            "一些",
            "需要",
            "应该",
            "能够",
            "使用",
            "通过",
            "进行",
            "实现",
            "添加",
            "修改",
            "删除",
            "支持",
            "提供",
            "包括",
            "用于",
            "the",
            "a",
            "an",
            "is",
            "are",
            "be",
            "to",
            "of",
            "in",
            "for",
            "and",
            "or",
            "not",
            "this",
            "that",
            "with",
            "from",
            "will",
            "can",
            "should",
            "it",
            "we",
            "you",
            "as",
            "if",
            "but",
            "so",
            "all",
            "no",
            "on",
            "at",
        }

        # 技术关键词——CamelCase/snake_case/中文技术词
        keywords: list[str] = []
        # 1. 提取英文标识符（CamelCase/snake_case）
        for word in prd_text.replace("\n", " ").split():
            word = word.strip(".,;:()[]{}<>\"'`/\\|!@#$%^&*+-=~")
            if len(word) < 2:
                continue
            # 标识符模式：含大写字母或下划线
            if any(c.isupper() for c in word) or "_" in word:
                if word.lower() not in _stop:
                    keywords.append(word)
        # 2. 提取中文技术词（2-6 个汉字）
        import re as _re

        cn_terms = _re.findall(r"[一-鿿]{2,6}", prd_text)
        for t in cn_terms:
            if t not in _stop and t not in keywords:
                keywords.append(t)
        # 去重 + 限制数量
        seen: set[str] = set()
        uniq = []
        for k in keywords:
            if k.lower() not in seen:
                seen.add(k.lower())
                uniq.append(k)
        # 最多 20 个关键词，避免 prompt 膨胀
        return uniq[:20]


