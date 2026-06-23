"""Step 7.2 健康指标聚合器。

聚合所有核心组件的健康状态——供运维仪表盘和 Prometheus 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ComponentStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """单个组件的健康信息。"""

    name: str
    status: ComponentStatus = ComponentStatus.UNKNOWN
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


class HealthCollector:
    """健康指标聚合器——注册组件 + 采集 + 汇总。"""

    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}

    def register(self, name: str) -> ComponentHealth:
        """注册组件（初始状态 UNKNOWN）。"""
        h = ComponentHealth(name=name)
        self._components[name] = h
        return h

    def update(
        self,
        name: str,
        status: ComponentStatus,
        message: str = "",
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """更新组件状态。"""
        if name not in self._components:
            self.register(name)
        c = self._components[name]
        c.status = status
        c.message = message
        if metrics:
            c.metrics.update(metrics)

    def get(self, name: str) -> ComponentHealth | None:
        return self._components.get(name)

    def list_all(self) -> list[ComponentHealth]:
        return list(self._components.values())

    def overall_status(self) -> ComponentStatus:
        """汇总所有组件状态。

        - 任何 UNHEALTHY → UNHEALTHY
        - 任何 DEGRADED → DEGRADED
        - 全部 HEALTHY → HEALTHY
        """
        statuses = [c.status for c in self._components.values()]
        if not statuses:
            return ComponentStatus.UNKNOWN
        if any(s == ComponentStatus.UNHEALTHY for s in statuses):
            return ComponentStatus.UNHEALTHY
        if any(s == ComponentStatus.DEGRADED for s in statuses):
            return ComponentStatus.DEGRADED
        if all(s == ComponentStatus.HEALTHY for s in statuses):
            return ComponentStatus.HEALTHY
        return ComponentStatus.UNKNOWN

    def summary(self) -> dict[str, Any]:
        """生成健康摘要——供 API 返回。"""
        return {
            "overall": self.overall_status().value,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "metrics": c.metrics,
                }
                for c in self._components.values()
            ],
        }
