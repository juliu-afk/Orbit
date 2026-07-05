"""元认知层 (Metacognitive Monitor)——Agent 决策质量的独立监控系统。

Phase A (Agent 五大能力追赶): v0.26
对标: AgentDebug (UIUC+Stanford+AMD), VIGIL, Metacognitive Layer

核心组件:
  - Monitor: 独立 asyncio Task，消费 StreamEvent，运行触发器
  - Triggers: GoalDriftDetector, RepetitionDetector, LatencyWatchdog
  - Classifier: AgentErrorTaxonomy 错误分类
  - HITL: 人工移交管理器

设计原则:
  - Monitor 崩溃 → 主 Agent 退化到不加 Monitor 的基线，不会更差
  - 规则触发器优先（快+便宜），LLM 验证兜底（语义判断）
  - fail-open: 所有检查失败不阻塞主 Agent
"""

from orbit.metacognition.classifier import AgentErrorCategory, ErrorClassifier
from orbit.metacognition.hitl import HITLManager, HITLRequest, HITLResponse
from orbit.metacognition.monitor import MonitorAgent
from orbit.metacognition.triggers import (
    Alert,
    AlertType,
    GoalDriftDetector,
    LatencyWatchdog,
    RepetitionDetector,
    TriggerEngine,
)

__all__ = [
    "MonitorAgent",
    "TriggerEngine",
    "GoalDriftDetector",
    "RepetitionDetector",
    "LatencyWatchdog",
    "Alert",
    "AlertType",
    "ErrorClassifier",
    "AgentErrorCategory",
    "HITLManager",
    "HITLRequest",
    "HITLResponse",
]
