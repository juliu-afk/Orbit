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

    # P1 RSCK-7: 最大组件数——防止无界注册导致内存泄漏
    _MAX_COMPONENTS = 500

    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}
        self._registration_order: list[str] = []

    def register(self, name: str) -> ComponentHealth:
        """注册组件（初始状态 UNKNOWN）。

        P1 RSCK-7: 超限时淘汰最旧注册——防止长时间运行 OOM。
        """
        # 已注册则更新
        if name in self._components:
            return self._components[name]
        # 超限淘汰——FIFO 移除最旧
        while len(self._components) >= self._MAX_COMPONENTS and self._registration_order:
            _old = self._registration_order.pop(0)
            self._components.pop(_old, None)
        h = ComponentHealth(name=name)
        self._components[name] = h
        self._registration_order.append(name)
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
