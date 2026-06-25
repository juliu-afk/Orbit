"""Dashboard 推送事件数据模型。

WHY 独立于 API schemas：
事件模型面向实时推送，字段精简；API schemas 面向请求/响应，字段完整。
职责不同，避免耦合。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DashboardEvent(BaseModel):
    """事件基类。

    type 区分事件类型（task:update / token:update / alert:new），
    前端通过 type 路由到不同 Store。
    """

    type: str
    task_id: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskUpdatePayload(BaseModel):
    """task:update 事件 payload。

    携带任务状态 + DAG 节点列表（简化版 GraphNode）。
    dag 字段用 list[dict] 而非 Pydantic 嵌套模型——
    减少序列化开销，前端自行解析。
    """

    task_id: str
    state: str  # TaskState value
    progress: float
    dag: list[dict[str, Any]]  # 简化 GraphNode：{id, agent_role, status, duration_ms, error}
    timestamp: str


class TokenUpdatePayload(BaseModel):
    """token:update 事件 payload。

    每次 LLM 调用完成后推送，前端 ECharts 追加数据点。
    """

    task_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    timestamp: str


class AlertPayload(BaseModel):
    """alert:new 事件 payload。

    level: HallucinationLevel 值（l1_graph/l3_entropy/l8_config 等）
    severity: warning 需关注/critical 需立即处理
    """

    task_id: str
    level: str  # HallucinationLevel value
    severity: Literal["warning", "critical"]
    message: str
    timestamp: str


class MetricsPayload(BaseModel):
    """metrics:snapshot 事件 payload。

    定时（每 5s）推送到驾驶舱，前端 ECharts 刷新指标面板。
    """

    task_id: str  # "_system" 表示全局指标
    snapshot: dict[str, Any]  # 来自 metrics.snapshot()
    timestamp: str


class AgentOpsAlertPayload(BaseModel):
    """agentops:alert 事件 payload（Step 7.2 告警引擎）。

    severity: warning 需关注 / critical 需立即处理
    """

    task_id: str
    alert_name: str
    severity: Literal["warning", "critical"]
    message: str
    metrics_snapshot: dict[str, Any]
    timestamp: str
