"""Step 5.2 多 Agent 角色定义 (Phase 1 升级).

5 个核心角色 + 需求澄清 Agent。
AgentFactory 根据角色返回实例，调度器按节点 agent_role 分配。

Phase 1: Architect/Developer/Reviewer/QA → ReActAgent (think→act→observe 循环)
"""

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.factory import AgentFactory
from orbit.agents.react_agent import IterationBudget, ReActAgent

__all__ = [
    "AgentFactory",
    "AgentInput",
    "AgentOutput",
    "AgentRole",
    "BaseAgent",
    "IterationBudget",
    "ReActAgent",
]
