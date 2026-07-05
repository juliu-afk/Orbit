"""AgentErrorTaxonomy——Agent 错误分类体系。

对标: AgentDebug (UIUC+Stanford+AMD)——结构化智能体错误分类

六类 Agent 级错误（区别于代码级 hallucination）:
  GOAL_FORGETTING:  目标遗忘——Agent 忘记原始任务
  CONTEXT_CONFUSION: 上下文混淆——历史步骤混为一谈
  TOOL_MISUSE:       工具误用——调错工具或参数错误
  REFLECTION_FAILURE: 反思失误——误判任务完成状态
  PLANNING_DEVIATION: 规划偏差——分解出现混乱
  RESOURCE_EXHAUSTION: 资源耗尽——Token/时间超限
"""

from __future__ import annotations

from enum import StrEnum

from orbit.metacognition.triggers import Alert, AlertType


class AgentErrorCategory(StrEnum):
    GOAL_FORGETTING = "goal_forgetting"
    CONTEXT_CONFUSION = "context_confusion"
    TOOL_MISUSE = "tool_misuse"
    REFLECTION_FAILURE = "reflection_failure"
    PLANNING_DEVIATION = "planning_deviation"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


# Alert 类型 → ErrorCategory 的映射
_ALERT_TO_ERROR: dict[AlertType, AgentErrorCategory] = {
    AlertType.GOAL_DRIFT: AgentErrorCategory.GOAL_FORGETTING,
    AlertType.REPETITION: AgentErrorCategory.PLANNING_DEVIATION,
    AlertType.LATENCY: AgentErrorCategory.RESOURCE_EXHAUSTION,
    AlertType.RESOURCE_EXHAUSTION: AgentErrorCategory.RESOURCE_EXHAUSTION,
}


class ErrorClassifier:
    """将 Monitor 告警分类到标准错误类型。

    用法:
        classifier = ErrorClassifier()
        category = classifier.classify(alert)
        logger.info("agent_error", category=category, alert=alert.message)
    """

    def classify(self, alert: Alert) -> AgentErrorCategory:
        """将告警映射到 AgentErrorTaxonomy 分类。"""
        return _ALERT_TO_ERROR.get(
            alert.type, AgentErrorCategory.PLANNING_DEVIATION
        )

    def classify_batch(self, alerts: list[Alert]) -> dict[AgentErrorCategory, int]:
        """批量分类——返回每种错误类型的计数。"""
        counts: dict[AgentErrorCategory, int] = {}
        for alert in alerts:
            cat = self.classify(alert)
            counts[cat] = counts.get(cat, 0) + 1
        return counts
