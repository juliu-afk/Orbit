"""告警规则引擎（Step 7.2 AgentOps）。

纯内存规则引擎——参考 compliance/rule_engine.py 模式。
评估指标快照 → 阈值超标时通过 EventBus 推送告警事件。
内置冷却机制：同一规则触发后冷却期内不重复推送。

生产部署时 AlertManager rules.yml 提供等效规则，
本引擎用于 MVP 单进程零依赖场景。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from orbit.observability.config import agentops_config

logger = structlog.get_logger("orbit.alerts")


class AlertSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """告警规则定义。

    condition 签名：(metrics_snapshot: dict) -> bool
    """

    name: str
    description: str
    severity: AlertSeverity
    condition: Callable[[dict[str, Any]], bool]
    cooldown_seconds: int = 300


@dataclass
class Alert:
    """一条触发的告警。"""

    name: str
    severity: AlertSeverity
    message: str
    triggered_at: float  # time.time()
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)


class AlertEngine:
    """告警规则引擎。

    用法：
        engine = AlertEngine(event_bus=bus)
        engine.add_builtin_rules()
        alerts = engine.evaluate(metrics.snapshot())
        # alerts 内的告警已自动通过 EventBus 推送
    """

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        # 冷却追踪：rule_name → 上次触发时间
        self._last_triggered: dict[str, float] = {}
        # 历史告警（内存环形缓冲，最多 200 条）
        self._history: list[Alert] = []

    def register(self, rule: AlertRule) -> None:
        self._rules[rule.name] = rule

    def add_builtin_rules(self) -> None:
        """注册内置 5 条告警规则。

        WHY 内置而非外置配置：MVP 阶段规则固定，
        硬编码避免 YAML 解析依赖和文件路径问题。
        后续可改为从 YAML 文件加载。
        """
        self.register(
            AlertRule(
                name="high_token_consumption",
                description="单任务 Token 消耗超过阈值",
                severity=AlertSeverity.WARNING,
                condition=lambda m: (
                    m.get("llm_tokens_total", {}).get("input", 0)
                    + m.get("llm_tokens_total", {}).get("output", 0)
                    > agentops_config.TOKEN_THRESHOLD_WARNING
                ),
                cooldown_seconds=agentops_config.ALERT_COOLDOWN_SECONDS,
            )
        )
        self.register(
            AlertRule(
                name="high_entropy",
                description="LLM 输出熵值异常偏高，可能存在幻觉风险",
                severity=AlertSeverity.WARNING,
                condition=lambda m: m.get("entropy_bits", 0)
                > agentops_config.ENTROPY_BITS_THRESHOLD,
                cooldown_seconds=agentops_config.ALERT_COOLDOWN_SECONDS,
            )
        )
        self.register(
            AlertRule(
                name="sandbox_pool_exhausted",
                description="沙箱池可用实例为 0，新任务无法执行",
                severity=AlertSeverity.CRITICAL,
                condition=lambda m: m.get("sandbox_pool_available", -1) == 0,
                # -1 = 未初始化（MVP 无沙箱池），不告警；0 = 真正耗尽
                cooldown_seconds=60,
            )
        )
        self.register(
            AlertRule(
                name="config_drift",
                description="检测到配置漂移，需人工确认是否回滚",
                severity=AlertSeverity.CRITICAL,
                condition=lambda m: m.get("config_drift_detected", 0) == 1,
                cooldown_seconds=0,  # 配置漂移每次检测到都告警
            )
        )
        self.register(
            AlertRule(
                name="circuit_breaker_open",
                description="熔断器已打开，LLM 调用被拦截",
                severity=AlertSeverity.CRITICAL,
                condition=lambda m: any(
                    v == 1 for v in m.get("circuit_breaker_state", {}).values()
                ),
                cooldown_seconds=120,
            )
        )

    def evaluate(self, metrics: dict[str, Any]) -> list[Alert]:
        """评估所有规则，返回当前触发的告警列表。

        自动应用冷却机制：同一规则冷却期内不重复触发。
        """
        triggered: list[Alert] = []
        now = time.time()

        for rule in self._rules.values():
            try:
                hit = rule.condition(metrics)
            except Exception:
                logger.warning("alert_rule_eval_error", rule=rule.name, exc_info=True)
                continue

            if not hit:
                continue

            # 冷却检查
            last = self._last_triggered.get(rule.name, 0)
            if rule.cooldown_seconds > 0 and (now - last) < rule.cooldown_seconds:
                continue

            alert = Alert(
                name=rule.name,
                severity=rule.severity,
                message=rule.description,
                triggered_at=now,
                metrics_snapshot=metrics,
            )
            triggered.append(alert)
            self._last_triggered[rule.name] = now

            # 记录历史（环形缓冲）
            self._history.append(alert)
            if len(self._history) > 200:
                self._history = self._history[-200:]

            logger.warning(
                "alert_triggered",
                rule=rule.name,
                severity=rule.severity.value,
                message=rule.description,
            )

        return triggered

    def get_active(self) -> list[dict[str, Any]]:
        """返回当前活跃告警（冷却期内的告警仍视为活跃）。"""
        now = time.time()
        active: list[dict[str, Any]] = []
        for name, last in self._last_triggered.items():
            rule = self._rules.get(name)
            if rule is None:
                continue
            if rule.cooldown_seconds == 0 or (now - last) < rule.cooldown_seconds:
                active.append(
                    {
                        "name": name,
                        "severity": rule.severity.value,
                        "message": rule.description,
                        "since": last,
                    }
                )
        return active

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回告警历史。"""
        return [
            {
                "name": a.name,
                "severity": a.severity.value,
                "message": a.message,
                "triggered_at": a.triggered_at,
            }
            for a in self._history[-limit:]
        ]
