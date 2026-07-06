"""高峰避让调度器——OffPeakScheduler 协调器。

PeakWindowManager 见 peak_window.py，DeferredQueue 见 deferred_queue.py。
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import structlog
from typing import TYPE_CHECKING, cast

from orbit.scheduler.offpeak.deferred_queue import DeferredQueue
from orbit.scheduler.offpeak.peak_window import PeakWindowManager
from orbit.scheduler.offpeak_models import (
    DeferredStatus,
    DeferredTask,
    EnqueueResult,
    PeakStatus,
    PeakWindow,
    ProviderPeakConfig,
)

if TYPE_CHECKING:
    from orbit.goal.models import GoalSession
    from orbit.goal.meta_orchestrator import MetaOrchestrator
    from orbit.goal.preflight import PreFlightEstimator

logger = structlog.get_logger("orbit.offpeak")

# 默认高峰配置——YAML 加载失败时的兜底
DEFAULT_PEAK_CONFIGS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "timezone": "Asia/Shanghai",
        "peak_windows": [{"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "09:00-23:00"}],
        "offpeak_windows": [
            {"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "23:00-09:00"},
            {"days": ["Sat","Sun"], "hours": "00:00-24:00"},
        ],
        "peak_price_multiplier": 1.0,
        "offpeak_price_multiplier": 0.7,
    },
    "anthropic": {
        "timezone": "America/Los_Angeles",
        "peak_windows": [{"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "08:00-18:00"}],
        "offpeak_windows": [
            {"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "18:00-08:00"},
            {"days": ["Sat","Sun"], "hours": "00:00-24:00"},
        ],
        "peak_price_multiplier": 1.0,
        "offpeak_price_multiplier": 0.85,
    },
}


# ── OffPeakScheduler ───────────────────────────────────────────

def estimate_window_capacity(
    window_start: datetime,
    window_end: datetime,
    queued_tasks: list[DeferredTask],
    max_parallel: int = 5,
) -> int:
    """估算低峰窗口能跑几个任务。

    WHY 悲观估算: 用预估耗时的 1.3x 做 buffer。
    WHY 短任务优先: 最大化吞吐——先跑小任务填满窗口。
    """
    window_seconds = (window_end - window_start).total_seconds()
    sorted_tasks = sorted(
        queued_tasks,
        key=lambda t: (
            0 if t.priority in ("CRITICAL", "HIGH") else 1,
            t.estimated_duration_seconds,
        ),
    )
    remaining = window_seconds * max_parallel
    count = 0
    for task in sorted_tasks:
        cost = task.estimated_duration_seconds * 1.3
        if remaining >= cost:
            remaining -= cost
            count += 1
        else:
            break
    return count


class OffPeakScheduler:
    """高峰避让调度器——协调 PeakWindowManager + DeferredQueue + MetaOrchestrator。

    Usage:
        offpeak = OffPeakScheduler(peak_mgr, queue, orchestrator, preflight)
        await offpeak.start()  # 启动后台 window_watcher
        result = await offpeak.enqueue(goal)  # 排队 Goal
    """

    def __init__(
        self,
        peak_manager: PeakWindowManager,
        queue: DeferredQueue,
        orchestrator: MetaOrchestrator,
        preflight: PreFlightEstimator,
    ) -> None:
        self._peak = peak_manager
        self._queue = queue
        self._orch = orchestrator
        self._preflight = preflight
        self._watcher_task: asyncio.Task | None = None
        self._force_offpeak_only = os.getenv("ORBIT_OFFPEAK_ONLY", "") == "true"
        self._watcher_interval = int(os.getenv("ORBIT_OFFPEAK_WATCHER_INTERVAL", "60"))

    # ── 公共属性（供 schedule.py API 路由使用） ──

    @property
    def peak_manager(self):
        return self._peak

    @property
    def queue(self):
        return self._queue

    @property
    def orchestrator(self):
        return self._orch

    # ── 公共 API ──

    async def enqueue(self, goal: GoalSession) -> EnqueueResult:
        """将 Goal 排队到低峰窗口。

        流程:
        1. 调 PreFlightEstimator 预估 token/时间
        2. 判定当前是否高峰 → 确定目标窗口
        3. 构造 DeferredTask → push 到队列

        ORBIT_OFFPEAK_ONLY + 高峰 + 非紧急:
        返回 peak_warning 警告——提示用户确认紧急或等待低峰。
        """
        now = datetime.now(UTC)
        provider = getattr(goal, "target_provider", "") or "deepseek"

        # ── ORBIT_OFFPEAK_ONLY 高峰警告 ──
        if self._force_offpeak_only and self._peak.is_peak(provider, now):
            urgent_flag = getattr(goal, "urgent", False)
            if not urgent_flag:
                next_window = self._peak.next_offpeak_window(provider, now)
                next_start = ""
                if next_window:
                    next_start = next_window.starts_at_iso
                return EnqueueResult(
                    goal_id=goal.id,
                    status="peak_warning",
                    warning_message=(
                        f"当前为 {provider} 高峰期。"
                        f"若需立即执行，请设 urgent=true 后重新提交。"
                        f"下一个低峰窗口: {next_start}"
                    ),
                )

        # ── 预估 ──
        estimate = await self._preflight.estimate(goal.description)
        avg_tokens = (estimate.token_low + estimate.token_high) // 2
        avg_duration = (estimate.time_low_seconds + estimate.time_high_seconds) // 2

        # ── 确定目标窗口 ──
        window = self._peak.next_offpeak_window(provider, now)
        if window is None:
            # 极端情况: 无低峰窗口定义 → 立即执行
            logger.warning("no_offpeak_window_found", provider=provider, goal_id=goal.id)
            task = asyncio.create_task(self._orch.run(goal))
            return EnqueueResult(
                goal_id=goal.id,
                status="released",
                    target_window_start="now",
                    target_window_end="now",
                    queue_position=0,
                )

        # 构造 DeferredTask
        task = DeferredTask(
            id=goal.id,
            goal_description=goal.description,
            priority=getattr(goal, "priority", "NORMAL"),
            provider=provider,
            estimated_tokens=avg_tokens,
            estimated_duration_seconds=avg_duration,
            target_window_start=window.starts_at_iso,
            target_window_end=window.ends_at_iso,
            status="queued",
            created_at=now.isoformat(),
            goal_json=goal.model_dump_json(),
        )
        position = await self._queue.push(task)

        logger.info(
            "goal_enqueued_offpeak",
            goal_id=goal.id,
            provider=provider,
            target_window=task.target_window_start,
            position=position,
        )
        return EnqueueResult(
            goal_id=goal.id,
            status="queued",
            target_window_start=task.target_window_start,
            target_window_end=task.target_window_end,
            queue_position=position,
        )

    async def start(self) -> None:
        """启动后台窗口监视协程。

        恢复数据库中处于 released/running 状态的僵尸任务
        （上次关闭时窗口已释放但未完成的）。
        """
        # 恢复僵尸任务
        released = await self._queue.list_all("released")
        for task in released:
            await self._queue.mark_cancelled(task.id)
            logger.warning("zombie_task_cleaned", goal_id=task.id, reason="stale_released_on_restart")

        self._watcher_task = asyncio.create_task(self._window_watcher())
        logger.info("offpeak_scheduler_started", watcher_interval=self._watcher_interval)

    async def stop(self) -> None:
        """停止 watcher 协程。"""
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    @property
    def force_offpeak_only(self) -> bool:
        return self._force_offpeak_only

    # ── 后台协程 ──

    async def _window_watcher(self) -> None:
        """后台协程: 按可配置间隔检查低峰窗口。

        WHY 可配置间隔: 生产环境可能需要更频繁检查（30s），
        开发环境默认 60s 足够。
        """
        while True:
            try:
                await self._check_windows()
            except Exception:
                logger.exception("window_watcher_error")
            await asyncio.sleep(self._watcher_interval)

    async def _check_windows(self) -> None:
        """检查所有活跃厂商的低峰窗口——释放到期任务。"""
        now = datetime.now(UTC)

        for provider in self._peak.providers:
            # 查找所有 queued 任务的目标窗口
            all_queued = await self._queue.list_all("queued")
            provider_tasks = [t for t in all_queued if t.provider == provider]
            if not provider_tasks:
                continue

            # 按目标窗口分桶
            windows: dict[str, list[DeferredTask]] = {}
            for task in provider_tasks:
                key = task.target_window_start
                if key not in windows:
                    windows[key] = []
                windows[key].append(task)

            for window_start_iso, tasks in windows.items():
                try:
                    window_start = datetime.fromisoformat(window_start_iso)
                except (ValueError, TypeError):
                    continue

                # 窗口结束后 30 分钟仍未释放 → 跳过（可能是过期窗口）
                minutes_since_start = (now - window_start).total_seconds() / 60
                if minutes_since_start < 0:
                    continue  # 窗口还没到

                # 取第一个任务的 target_window_end
                window_end_iso = tasks[0].target_window_end
                try:
                    window_end = datetime.fromisoformat(window_end_iso)
                except (ValueError, TypeError):
                    window_end = window_start + timedelta(hours=10)

                # 窗口已结束 >30min → 跳过，任务标记为过期
                if now > window_end + timedelta(minutes=30):
                    for task in tasks:
                        await self._queue.mark_cancelled(task.id)
                        logger.warning(
                            "window_expired_task_cancelled",
                            goal_id=task.id,
                            window_start=window_start_iso,
                        )
                    continue

                # 窗口正在运行中 → 计算容量并释放
                if now >= window_start:
                    capacity = estimate_window_capacity(window_start, window_end, tasks)
                    if capacity > 0:
                        released = await self._queue.pop_for_window(
                            window_start_iso, window_end_iso, limit=capacity
                        )
                        for task in released:
                            try:
                                from orbit.goal.models import GoalSession
                                goal = GoalSession.model_validate_json(task.goal_json)
                                bg = asyncio.create_task(self._orch.run(goal))
                                bg.add_done_callback(
                                    lambda t, dt=task: asyncio.ensure_future(
                                        self._on_task_done(t, dt)
                                    )
                                )
                                logger.info(
                                    "offpeak_task_released",
                                    goal_id=task.id,
                                    provider=provider,
                                )
                            except Exception:
                                logger.exception(
                                    "offpeak_task_release_failed",
                                    goal_id=task.id,
                                )

                # 窗口结束前 10 分钟: 容量不够则顺延
                minutes_to_end = (window_end - now).total_seconds() / 60
                if 0 < minutes_to_end <= 10:
                    capacity = estimate_window_capacity(now, window_end, tasks)
                    if capacity < len(tasks):
                        next_window = self._peak.next_offpeak_window(provider, after=window_end)
                        if next_window:
                            overflow = tasks[capacity:]
                            for task in overflow:
                                await self._queue.reschedule(
                                    task.id,
                                    next_window.starts_at_iso,
                                    next_window.ends_at_iso,
                                )
                            logger.warning(
                                "window_overflow_rescheduled",
                                provider=provider,
                                overflow_count=len(overflow),
                            )

    async def _on_task_done(
        self, t: asyncio.Task, deferred_task: DeferredTask
    ) -> None:
        """Goal 执行完毕回调——记录实际消耗和成本节省。"""
        try:
            result = t.result()
            # 计算成本节省
            provider = deferred_task.provider
            peak_price = self._peak.get_price_multiplier(provider) if self._peak.is_peak(provider) else 1.0
            offpeak_price = self._peak.get_price_multiplier(provider)
            # 简化: 用 1K tokens 基础价格 × 倍数 × tokens
            from orbit.gateway.routing import _MODEL_COSTS
            base_price = _MODEL_COSTS.get(provider, 0.001)
            peak_cost = deferred_task.estimated_tokens / 1000 * base_price * peak_price
            offpeak_cost = deferred_task.estimated_tokens / 1000 * base_price * offpeak_price
            saved = round(max(0, peak_cost - offpeak_cost), 4)

            await self._queue.mark_done(
                deferred_task.id,
                actual_tokens=getattr(result, "total_tokens", 0),
                cost_saved=saved,
            )
        except Exception:
            logger.exception("task_done_callback_failed", goal_id=deferred_task.id)
