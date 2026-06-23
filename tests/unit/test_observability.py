"""Step 7.2 HealthCollector 单元测试。"""

import pytest

from orbit.observability.collector import (
    ComponentStatus,
    HealthCollector,
)


class TestHealthCollector:
    """健康指标聚合器——注册/更新/汇总/摘要。"""

    @pytest.fixture
    def collector(self) -> HealthCollector:
        return HealthCollector()

    def test_register(self, collector: HealthCollector) -> None:
        collector.register("scheduler")
        assert collector.get("scheduler") is not None
        assert collector.get("scheduler").status == ComponentStatus.UNKNOWN

    def test_update_status(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, "OK")
        assert collector.get("test").status == ComponentStatus.HEALTHY
        assert collector.get("test").message == "OK"

    def test_update_metrics(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, metrics={"latency_ms": 5})
        assert collector.get("test").metrics["latency_ms"] == 5

    def test_overall_all_healthy(self, collector: HealthCollector) -> None:
        for name in ["a", "b"]:
            collector.register(name)
            collector.update(name, ComponentStatus.HEALTHY)
        assert collector.overall_status() == ComponentStatus.HEALTHY

    def test_overall_one_degraded(self, collector: HealthCollector) -> None:
        collector.register("a")
        collector.update("a", ComponentStatus.HEALTHY)
        collector.register("b")
        collector.update("b", ComponentStatus.DEGRADED)
        assert collector.overall_status() == ComponentStatus.DEGRADED

    def test_overall_one_unhealthy(self, collector: HealthCollector) -> None:
        collector.register("a")
        collector.update("a", ComponentStatus.HEALTHY)
        collector.register("b")
        collector.update("b", ComponentStatus.UNHEALTHY)
        assert collector.overall_status() == ComponentStatus.UNHEALTHY

    def test_overall_empty(self, collector: HealthCollector) -> None:
        assert collector.overall_status() == ComponentStatus.UNKNOWN

    def test_summary_format(self, collector: HealthCollector) -> None:
        collector.register("test")
        collector.update("test", ComponentStatus.HEALTHY, "ok", {"key": 1})
        s = collector.summary()
        assert s["overall"] == "healthy"
        assert len(s["components"]) == 1
        assert s["components"][0]["metrics"]["key"] == 1

    def test_list_all(self, collector: HealthCollector) -> None:
        for name in ["x", "y", "z"]:
            collector.register(name)
        assert len(collector.list_all()) == 3
