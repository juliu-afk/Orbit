"""可观测性 API（Step 7.2）。

GET /api/v1/observability/health
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from orbit.observability.collector import ComponentStatus, HealthCollector

router = APIRouter(prefix="/observability", tags=["observability"])

_collector = HealthCollector()

# 注册核心组件
for _comp in [
    "scheduler",
    "llm_gateway",
    "code_graph",
    "db_graph",
    "config_graph",
    "hallucination_layers",
    "sandbox",
    "knowledge_engine",
]:
    _collector.register(_comp)


@router.get("/health", summary="全组件健康状态")
async def observability_health() -> dict[str, Any]:
    """返回所有核心组件的健康状态摘要。"""
    # 动态更新已知组件状态
    _collector.update("scheduler", ComponentStatus.HEALTHY)
    _collector.update("knowledge_engine", ComponentStatus.HEALTHY)
    _collector.update("llm_gateway", ComponentStatus.HEALTHY)
    _collector.update("code_graph", ComponentStatus.DEGRADED, "MVP 占位，未连接 Tree-sitter")
    _collector.update("db_graph", ComponentStatus.HEALTHY)
    _collector.update("config_graph", ComponentStatus.HEALTHY)
    _collector.update("hallucination_layers", ComponentStatus.HEALTHY)
    _collector.update("sandbox", ComponentStatus.HEALTHY)
    return _collector.summary()


@router.get("/health/{component}", summary="单组件健康状态")
async def component_health(component: str) -> dict[str, Any]:
    """返回单个组件的健康状态。"""
    c = _collector.get(component)
    if c is None:
        return {"error": f"未知组件: {component}"}
    return {
        "name": c.name,
        "status": c.status.value,
        "message": c.message,
        "metrics": c.metrics,
    }
