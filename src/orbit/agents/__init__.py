"""Step 5.2 多 Agent 角色定义。

5 个核心角色：Architect / Developer / Reviewer / QA / ConfigManager。
AgentFactory 根据角色返回实例，调度器按节点 agent_role 分配。
"""

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.factory import AgentFactory

__all__ = [
    "AgentFactory",
    "AgentInput",
    "AgentOutput",
    "AgentRole",
    "BaseAgent",
]
