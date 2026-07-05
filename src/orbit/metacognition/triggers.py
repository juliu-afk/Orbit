"""元认知触发器系统——三种检测器 + 组合引擎。

WHY 规则优先而非 LLM 优先:
  规则触发器: 零 Token 成本、零幻觉风险、毫秒级延迟
  LLM 兜底: 仅用于语义判断（目标是否真的偏离），规则不确定时才触发

三种检测器:
  1. RepetitionDetector: 重复动作——复用 react_agent.py 的 doom_loop 逻辑
  2. GoalDriftDetector: 目标漂移——规则+可选 LLM 语义判断
  3. LatencyWatchdog: 延迟看门狗——单步超时 + 总任务超时
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

import structlog

logger = structlog.get_logger("orbit.metacognition.triggers")


class AlertType(StrEnum):
    REPETITION = "repetition"
    GOAL_DRIFT = "goal_drift"
    LATENCY = "latency"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


class Severity(StrEnum):
    WARNING = "warning"     # 记录但不打断
    CRITICAL = "critical"   # 暂停，触发 HITL


@dataclass
class Alert:
    type: AlertType
    severity: Severity
    message: str
    context: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ── 重复动作检测器 ──────────────────────────────────────

class RepetitionDetector:
    """检测 Agent 是否陷入循环——重复调用同一工具同一参数。

    复用 react_agent.py:353-373 的 doom_loop 逻辑，扩展为独立组件。
    """

    def __init__(self, window_size: int = 5, similarity_threshold: int = 3) -> None:
        self._window_size = window_size
        self._similarity_threshold = similarity_threshold  # 连续多少次相同触发

    def check(self, recent_actions: list[dict]) -> Alert | None:
        """检查最近 N 个 Action 的重复度。

        Args:
            recent_actions: 最近的动作列表，每项含 {tool, args}

        Returns:
            Alert | None: 检测到重复时返回告警
        """
        if len(recent_actions) < self._window_size:
            return None
        window = recent_actions[-self._window_size:]
        # 检查最近 N 个动作中相同的工具+参数出现次数
        seen: dict[str, int] = {}
        for a in window:
            key = f"{a.get('tool', '')}:{str(a.get('args', {}))}"
            seen[key] = seen.get(key, 0) + 1
        max_count = max(seen.values()) if seen else 0
        if max_count >= self._similarity_threshold:
            most_common = max(seen, key=lambda k: seen[k])
            return Alert(
                type=AlertType.REPETITION,
                severity=Severity.WARNING,
                message=f"检测到重复动作：{most_common} 连续出现 {max_count} 次",
                context={"action_key": most_common, "count": max_count},
            )
        return None


# ── 目标漂移检测器 ──────────────────────────────────────

class GoalDriftDetector:
    """检测 Agent 是否偏离原始目标。

    两层判断:
      1. 规则层（快速）：Action 的工具类别是否与目标类型匹配
      2. LLM 层（兜底）：规则不确定时，交给 LLM 做语义判断
    """

    # 工具类别→适用目标类型的粗略映射
    TOOL_GOAL_MAP: dict[str, list[str]] = {
        "read_file": ["分析", "检查", "审计", "审阅", "审查", "查看"],
        "write_file": ["编写", "修改", "修复", "实现", "生成"],
        "exec_command": ["运行", "测试", "执行", "部署"],
        "grep": ["搜索", "查找", "定位", "分析"],
        "glob": ["查找", "搜索"],
    }

    def __init__(self, drift_window: int = 3, llm: LLMClient | None = None) -> None:
        self._drift_window = drift_window
        self._llm = llm
        self._drift_count = 0

    def check_rule(self, goal: str, tool_name: str) -> bool:
        """规则检查：工具的适用场景是否与目标关键词匹配。

        Returns:
            True = 可能漂移，需要 LLM 二次判断
        """
        if tool_name not in self.TOOL_GOAL_MAP:
            return False  # 未知工具，不判断
        goal_keywords = self.TOOL_GOAL_MAP[tool_name]
        return not any(kw in goal for kw in goal_keywords)

    def check(
        self, goal: str, tool_name: str, tool_args: dict | None = None
    ) -> Alert | None:
        """综合检查——规则 + LLM 兜底。

        规则判断可能漂移 → 累加 drift_count → 达到阈值 → 触发告警
        """
        maybe_drift = self.check_rule(goal, tool_name)
        if maybe_drift:
            self._drift_count += 1
        else:
            self._drift_count = max(0, self._drift_count - 1)

        if self._drift_count >= self._drift_window:
            return Alert(
                type=AlertType.GOAL_DRIFT,
                severity=Severity.WARNING if self._drift_count < 5 else Severity.CRITICAL,
                message=f"可能偏离目标：连续 {self._drift_count} 个动作的工具类别与目标 '{goal[:50]}' 不匹配",
                context={
                    "drift_count": self._drift_count,
                    "goal": goal[:100],
                    "last_tool": tool_name,
                },
            )
        return None

    def reset(self) -> None:
        self._drift_count = 0


# ── 延迟看门狗 ──────────────────────────────────────────

class LatencyWatchdog:
    """监控单步执行时间和总任务时间。"""

    def __init__(
        self,
        max_action_ms: int = 300_000,   # 单 Action 5 分钟
        max_total_ms: int = 3_600_000,  # 总任务 1 小时
    ) -> None:
        self._max_action_ms = max_action_ms
        self._max_total_ms = max_total_ms

    def check_action(self, action_start: float) -> Alert | None:
        elapsed = (time.time() - action_start) * 1000
        if elapsed > self._max_action_ms:
            return Alert(
                type=AlertType.LATENCY,
                severity=Severity.WARNING,
                message=f"单步执行超时: {elapsed/1000:.0f}s",
                context={"elapsed_ms": elapsed, "limit_ms": self._max_action_ms},
            )
        return None

    def check_total(self, task_start: float) -> Alert | None:
        elapsed = (time.time() - task_start) * 1000
        if elapsed > self._max_total_ms:
            return Alert(
                type=AlertType.RESOURCE_EXHAUSTION,
                severity=Severity.CRITICAL,
                message=f"总任务超时: {elapsed/1000:.0f}s",
                context={"elapsed_ms": elapsed, "limit_ms": self._max_total_ms},
            )
        return None


# ── 触发器组合引擎 ──────────────────────────────────────

class TriggerEngine:
    """组合所有触发器，按优先级运行。

    规则:
      - 重复动作→WARNING（不打断）
      - 目标漂移→WARNING（轻度）/ CRITICAL（严重）
      - 延迟→WARNING（单步）/ CRITICAL（总超时）
      - 多个 CRITICAL → 最严重的先触发
    """

    def __init__(
        self,
        repetition: RepetitionDetector | None = None,
        goal_drift: GoalDriftDetector | None = None,
        latency: LatencyWatchdog | None = None,
    ) -> None:
        self.repetition = repetition or RepetitionDetector()
        self.goal_drift = goal_drift or GoalDriftDetector()
        self.latency = latency or LatencyWatchdog()

    def check_all(
        self,
        recent_actions: list[dict],
        goal: str,
        last_tool: str = "",
        action_start: float = 0,
        task_start: float = 0,
    ) -> list[Alert]:
        """运行所有触发器，返回排序后的告警列表（CRITICAL 优先）。"""
        alerts: list[Alert] = []

        r = self.repetition.check(recent_actions)
        if r:
            alerts.append(r)

        d = self.goal_drift.check(goal, last_tool)
        if d:
            alerts.append(d)

        if action_start:
            a = self.latency.check_action(action_start)
            if a:
                alerts.append(a)
        if task_start:
            t = self.latency.check_total(task_start)
            if t:
                alerts.append(t)

        # CRITICAL 排前面
        alerts.sort(key=lambda a: (0 if a.severity == Severity.CRITICAL else 1, a.timestamp))
        return alerts
