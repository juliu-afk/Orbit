"""Monitor Agent——独立于主 Agent 的元认知监控器。

WHY 独立:
  AgentDebug 研究证实 Agent 会在错误中自我循环而难以自察。
  需要一个独立于主 Agent 的次级 Monitor——它不执行任务，只监控执行任务
  的 Agent 是否在偏离目标、陷入循环、或即将超时。

设计:
  - 独立 asyncio Task，通过 Queue 消费 StreamEvent
  - 规则触发器优先（零 Token + 毫秒级）
  - 检测到 CRITICAL → 通过 HITLManager 通知前端
  - Monitor 自身崩溃 → 主 Agent 退化到不加 Monitor 的基线，不会更差

用法:
    monitor = MonitorAgent(hitl_manager=hitl, goal="检查2024年应收账款")
    monitor_task = asyncio.create_task(monitor.run(event_queue))
    # ... 主 Agent 运行 ...
    await event_queue.put(None)  # 信号: 主 Agent 完成
    await monitor_task
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.metacognition.hitl import HITLManager

import structlog

from orbit.metacognition.classifier import ErrorClassifier
from orbit.metacognition.triggers import (
    Alert,
    AlertType,
    GoalDriftDetector,
    LatencyWatchdog,
    RepetitionDetector,
    Severity,
    TriggerEngine,
)

logger = structlog.get_logger("orbit.metacognition.monitor")


class MonitorAgent:
    """元认知监控器——独立于主 Agent 的 asyncio Task。

    消费 StreamEvent，运行触发器，检测到 CRITICAL → HITL。

    Monitor 本身不是 LLM Agent——它是规则引擎+可选 LLM 验证的轻量组件。
    """

    # 最近保留的 Action 数量（供 RepetitionDetector 使用）
    _ACTION_HISTORY_SIZE = 10

    def __init__(
        self,
        goal: str = "",
        hitl_manager: HITLManager | None = None,
        triggers: TriggerEngine | None = None,
    ) -> None:
        self._goal = goal
        self._hitl = hitl_manager
        self._triggers = triggers or TriggerEngine()
        self._classifier = ErrorClassifier()

        # 运行时状态
        self._action_history: list[dict] = []
        self._task_start = 0.0
        self._action_start = 0.0
        self._alert_count: dict[AlertType, int] = {}
        self._task_id = ""

    async def run(self, event_queue: asyncio.Queue, task_id: str = "monitor") -> list[Alert]:
        """Monitor 主循环——消费事件直到收到 None（结束信号）。

        Args:
            event_queue: 主 Agent 推送 StreamEvent 的 asyncio.Queue
            task_id: 被监控的任务 ID

        Returns:
            整个监控期间产生的所有告警列表
        """
        self._task_id = task_id
        self._task_start = __import__("time").time()
        all_alerts: list[Alert] = []

        logger.debug("monitor_started", task_id=task_id, goal=self._goal[:80])

        try:
            while True:
                event = await event_queue.get()
                if event is None:  # 结束信号
                    break

                alerts = self._process_event(event)
                all_alerts.extend(alerts)

                for alert in alerts:
                    category = self._classifier.classify(alert)
                    self._alert_count[alert.type] = self._alert_count.get(alert.type, 0) + 1

                    logger.info(
                        "monitor_alert",
                        task_id=task_id,
                        type=alert.type.value,
                        severity=alert.severity.value,
                        category=category.value,
                        message=alert.message[:120],
                    )

                    if alert.severity == Severity.CRITICAL and self._hitl:
                        await self._trigger_hitl(task_id, alert)

        except Exception:
            logger.error("monitor_crashed", task_id=task_id, exc_info=True)

        logger.debug(
            "monitor_stopped",
            task_id=task_id,
            total_alerts=len(all_alerts),
            alert_counts={k.value: v for k, v in self._alert_count.items()},
        )
        return all_alerts

    def feed_action(self, tool_name: str, tool_args: dict | None = None) -> None:
        """主 Agent 执行了一个 Action → Monitor 记录并检查。

        供主 Agent 在每个 TOOL_CALL 后同步调用。
        """
        entry = {"tool": tool_name, "args": tool_args or {}}
        self._action_history.append(entry)
        if len(self._action_history) > self._ACTION_HISTORY_SIZE:
            self._action_history = self._action_history[-self._ACTION_HISTORY_SIZE:]
        self._action_start = __import__("time").time()

    def check_now(self, last_tool: str = "") -> list[Alert]:
        """主动检查——主 Agent 可在关键节点调用。

        Returns:
            当前检测到的所有告警
        """
        return self._triggers.check_all(
            recent_actions=self._action_history,
            goal=self._goal,
            last_tool=last_tool,
            action_start=self._action_start,
            task_start=self._task_start,
        )

    # ── 内部 ──────────────────────────────────────────

    def _process_event(self, event) -> list[Alert]:
        """处理单个 StreamEvent。"""
        event_type = getattr(event, "type", None)
        if event_type is None:
            return []

        # TURN_START → 重置漂移计数（新一轮开始了）
        if str(event_type) == "turn_start":
            if hasattr(self._triggers, "goal_drift"):
                self._triggers.goal_drift.reset()

        # TOOL_RESULT → 记录 Action + 运行触发器
        elif str(event_type) == "tool_result":
            data = getattr(event, "data", {}) or {}
            tool_name = data.get("tool", "")
            self.feed_action(tool_name)
            return self.check_now(last_tool=tool_name)

        return []

    async def _trigger_hitl(self, task_id: str, alert: Alert) -> None:
        """触发 HITL——通知前端并等待响应。"""
        if self._hitl is None:
            return
        try:
            from orbit.metacognition.hitl import HITLAction, HITLRequest

            request = HITLRequest(
                alert_type=alert.type.value,
                severity=alert.severity.value,
                message=alert.message,
                original_goal=self._goal,
                current_state=f"已执行 {len(self._action_history)} 个动作",
                context={
                    "recent_actions": [
                        f"{a.get('tool', '')}({str(a.get('args', {}))[:80]})"
                        for a in self._action_history[-5:]
                    ],
                    "alert_count": {k.value: v for k, v in self._alert_count.items()},
                },
            )
            await self._hitl.request_intervention(task_id, request)
        except Exception:
            logger.debug("hitl_trigger_failed", task_id=task_id, exc_info=True)
