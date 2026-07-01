"""Agent 工厂——AgentInput/AgentOutput。

用于创建确定性的 Agent 输入输出，模拟 Agent 执行结果。
"""

from __future__ import annotations

from typing import Any

from orbit.agents.base import AgentInput, AgentOutput, AgentRole


def create_agent_input(
    task: str = "测试需求：实现用户登录功能",
    context: dict[str, Any] | None = None,
    role: str | AgentRole = AgentRole.DEVELOPER,
    **kwargs: Any,
) -> AgentInput:
    """创建 AgentInput——Agent 统一输入。

    Args:
        task: 任务描述
        context: 上下文（上游节点输出、L1-L5 上下文等）
        role: Agent 角色（developer/architect/reviewer/qa/config_manager/clarifier/dream）
    """
    if context is None:
        context = {}

    if isinstance(role, str):
        role = AgentRole(role)

    return AgentInput(
        task=task,
        context=context,
        role=role,
    )


def create_agent_output(
    status: str = "ok",
    result: dict[str, Any] | None = None,
    error: str | None = None,
    turns: int = 3,
    tool_calls: int = 2,
    **kwargs: Any,
) -> AgentOutput:
    """创建 AgentOutput——Agent 统一输出。

    Args:
        status: 执行状态（ok/error）
        result: 执行结果（output/turns/tool_calls 等）
        error: 错误信息（status="error" 时）
        turns: ReAct 循环次数（便捷参数，写入 result）
        tool_calls: 工具调用次数（便捷参数，写入 result）
    """
    if result is None:
        result = {
            "output": "[mock] CODE_GENERATED_OK",
            "reasoning_chain": ["分析需求", "设计方案", "编写代码"],
            "turns": turns,
            "tool_calls": tool_calls,
        }

    return AgentOutput(
        status=status,
        result=result,
        error=error,
    )
