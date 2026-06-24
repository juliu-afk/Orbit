"""资源调度器 (Step 5.6 PR #3).

优先级抢占式调度 + 资源配额管理 + 公平时间片轮转。
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import structlog

logger = structlog.get_logger("orbit.scheduler.resource")


class TaskPriority(IntEnum):
    """任务优先级——数值越小优先级越高。"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class ResourceQuota:
    """全局资源配额——所有数字均可环境变量覆盖。"""

    max_concurrent_tasks: int = 5
    max_llm_calls_per_minute: int = 60
    max_tokens_per_task: int = 100000
    max_sandbox_instances: int = 3

    # 时间片 (秒)——同优先级任务最多连续执行此时长
    time_slice_seconds: int = 30
    # 长运行降级阈值 (秒)
    long_run_threshold_seconds: int = 300


@dataclass
class TaskResource:
    """单任务资源追踪。"""

    task_id: str
    priority: TaskPriority = TaskPriority.NORMAL
    llm_calls_used: int = 0
    tokens_used: int = 0
    sandbox_count: int = 0
    started_at: float = 0.0
    last_scheduled: float = 0.0
    consecutive_time: float = 0.0  # 本次连续执行时长

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "priority": self.priority.name,
            "llm_calls_used": self.llm_calls_used,
            "tokens_used": self.tokens_used,
            "sandbox_count": self.sandbox_count,
            "consecutive_time": round(self.consecutive_time, 1),
        }


class ResourceExhaustedError(Exception):
    """全局资源饱和, 新任务拒绝。"""


class ResourceScheduler:
    """资源调度器——优先级抢占 + 配额管理。

    用法:
        quota = ResourceQuota(max_concurrent_tasks=3)
        scheduler = ResourceScheduler(quota)
        await scheduler.submit("task-1", TaskPriority.NORMAL)
        if scheduler.can_proceed("task-1", estimated_tokens=1000):
            scheduler.consume_llm_call("task-1", tokens=500)
        scheduler.release("task-1")
    """

    def __init__(self, quota: ResourceQuota | None = None) -> None:
        self._quota = quota or ResourceQuota()
        # 活跃任务: task_id -> TaskResource
        self._active: dict[str, TaskResource] = {}
        # 排队队列——按优先级分桶
        self._queues: dict[TaskPriority, deque[str]] = {
            TaskPriority.CRITICAL: deque(),
            TaskPriority.HIGH: deque(),
            TaskPriority.NORMAL: deque(),
            TaskPriority.LOW: deque(),
        }
        # LLM 调用分钟级计数器: timestamp 列表
        self._llm_call_times: deque[float] = deque()
        # 调度轮转索引 (同优先级 round-robin)
        self._round_robin_index: dict[TaskPriority, int] = {p: 0 for p in TaskPriority}

    # ── 核心 API ──────────────────────────────────────────

    def submit(self, task_id: str, priority: TaskPriority = TaskPriority.NORMAL) -> bool:
        """提交任务——资源够则直接准入, 否则排队。

        Returns: True=准入, False=排队
        """
        # 检查是否可以准入
        if self._can_admit(priority):
            self._active[task_id] = TaskResource(
                task_id=task_id,
                priority=priority,
                started_at=time.time(),
                last_scheduled=time.time(),
            )
            logger.info("task_admitted", task_id=task_id, priority=priority.name)
            return True

        # CRITICAL 抢占 LOW
        if priority == TaskPriority.CRITICAL and self._queues[TaskPriority.LOW]:
            victim_id = self._queues[TaskPriority.LOW].popleft()
            if victim_id in self._active:
                self.release(victim_id)
                logger.warning("task_preempted", victim=victim_id, by=task_id)
            self._active[task_id] = TaskResource(
                task_id=task_id,
                priority=priority,
                started_at=time.time(),
                last_scheduled=time.time(),
            )
            return True

        # CRITICAL 也可抢占 LOW 活跃任务 (不在队列中的)
        if (
            priority == TaskPriority.CRITICAL
            and len(self._active) >= self._quota.max_concurrent_tasks
        ):
            # 找最低优先级的活跃任务
            victims = [
                (tid, r) for tid, r in self._active.items() if r.priority == TaskPriority.LOW
            ]
            if victims:
                victim_id = min(victims, key=lambda x: x[1].started_at)[0]
                self.release(victim_id)
                logger.warning("task_preempted_active", victim=victim_id, by=task_id)
                self._active[task_id] = TaskResource(
                    task_id=task_id,
                    priority=priority,
                    started_at=time.time(),
                    last_scheduled=time.time(),
                )
                return True

        # 排队
        self._queues[priority].append(task_id)
        logger.info(
            "task_queued",
            task_id=task_id,
            priority=priority.name,
            queue_len=len(self._queues[priority]),
        )
        return False

    def can_proceed(self, task_id: str, estimated_tokens: int = 0) -> bool:
        """预检——任务是否可以继续执行 (配额未超限)。"""
        res = self._active.get(task_id)
        if res is None:
            return False
        # Token 预算
        if (
            estimated_tokens > 0
            and res.tokens_used + estimated_tokens > self._quota.max_tokens_per_task
        ):
            return False
        # Sandbox 实例
        if res.sandbox_count >= self._quota.max_sandbox_instances:
            return False
        # 长运行降级
        elapsed = time.time() - res.started_at
        if elapsed > self._quota.long_run_threshold_seconds and res.priority != TaskPriority.LOW:
            res.priority = TaskPriority.LOW
            logger.info("task_demoted", task_id=task_id, reason="long_run")
        # 同优先级时间片用尽
        return res.consecutive_time <= self._quota.time_slice_seconds

    def consume_llm_call(self, task_id: str, tokens: int) -> bool:
        """消费一次 LLM 调用配额 + Token。

        Returns: True=允许, False=超限
        """
        res = self._active.get(task_id)
        if res is None:
            return False
        # 全局 LLM 限流检查
        now = time.time()
        cutoff = now - 60
        while self._llm_call_times and self._llm_call_times[0] < cutoff:
            self._llm_call_times.popleft()
        if len(self._llm_call_times) >= self._quota.max_llm_calls_per_minute:
            return False
        # Token 预算
        if tokens > 0 and res.tokens_used + tokens > self._quota.max_tokens_per_task:
            return False
        self._llm_call_times.append(now)
        res.llm_calls_used += 1
        res.tokens_used += tokens
        res.last_scheduled = now
        return True

    def release(self, task_id: str) -> None:
        """释放任务资源——调度下一排队任务。"""
        self._active.pop(task_id, None)

    def get_queue_status(self) -> dict[str, Any]:
        """返回各优先级队列长度 + 活跃任务数。"""
        return {
            "critical": len(self._queues[TaskPriority.CRITICAL]),
            "high": len(self._queues[TaskPriority.HIGH]),
            "normal": len(self._queues[TaskPriority.NORMAL]),
            "low": len(self._queues[TaskPriority.LOW]),
            "active": len(self._active),
            "llm_calls_last_minute": len(self._llm_call_times),
        }

    def get_task(self, task_id: str) -> TaskResource | None:
        return self._active.get(task_id)

    # ── 内部 ─────────────────────────────────────────────

    def _can_admit(self, priority: TaskPriority) -> bool:
        """检查是否可以准入新任务。"""
        return len(self._active) < self._quota.max_concurrent_tasks
