"""Step 5.2 Agent 角色 + 工厂测试。"""

from __future__ import annotations

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.factory import (
    AgentFactory,
    ArchitectAgent,
    ConfigManagerAgent,
    DeveloperAgent,
    QAAgent,
    ReviewerAgent,
)


def test_all_roles_registered() -> None:
    """5 个角色全部注册。"""
    for role in AgentRole:
        agent = AgentFactory.get_agent(role)
        assert agent.role == role


def test_factory_accepts_string() -> None:
    """工厂接受字符串角色名。"""
    agent = AgentFactory.get_agent("developer")
    assert isinstance(agent, DeveloperAgent)


def test_factory_unknown_role() -> None:
    """未知角色抛 ValueError。"""
    with pytest.raises(ValueError):
        AgentFactory.get_agent("nonexistent")


@pytest.mark.asyncio
async def test_developer_mock_output() -> None:
    """无 LLM 时返回 mock 结果。"""
    agent = DeveloperAgent()
    result = await agent.execute(AgentInput(task="写一个求和函数"))
    assert result.status == "ok"
    assert "code" in result.result


@pytest.mark.asyncio
async def test_architect_mock_output() -> None:
    agent = ArchitectAgent()
    result = await agent.execute(AgentInput(task="设计计算器应用"))
    assert "design" in result.result


@pytest.mark.asyncio
async def test_reviewer_mock_output() -> None:
    agent = ReviewerAgent()
    result = await agent.execute(AgentInput(task="def add(a,b): return a+b"))
    assert "review" in result.result


@pytest.mark.asyncio
async def test_qa_mock_output() -> None:
    agent = QAAgent()
    result = await agent.execute(AgentInput(task="def add(a,b): return a+b"))
    assert "tests" in result.result


@pytest.mark.asyncio
async def test_config_manager_mock_output() -> None:
    agent = ConfigManagerAgent()
    result = await agent.execute(AgentInput(task="设置数据库连接"))
    assert "config" in result.result


@pytest.mark.asyncio
async def test_agent_with_context() -> None:
    """上下文正确传递。"""
    agent = DeveloperAgent()
    result = await agent.execute(
        AgentInput(
            task="实现函数",
            context={"design": "求和函数: add(a,b) -> int", "task_id": "test-1"},
        )
    )
    assert result.status == "ok"


def test_agent_input_validation() -> None:
    """空 task 抛验证错误。"""
    with pytest.raises(ValueError):
        AgentInput(task="")


def test_agent_role_enum_values() -> None:
    """5 个角色枚举值正确。"""
    roles = list(AgentRole)
    assert len(roles) == 6
    assert AgentRole.ARCHITECT.value == "architect"
    assert AgentRole.DEVELOPER.value == "developer"
    assert AgentRole.REVIEWER.value == "reviewer"
    assert AgentRole.QA.value == "qa"
    assert AgentRole.CONFIG_MANAGER.value == "config_manager"


def test_custom_agent_registration() -> None:
    """自定义 Agent 可注册。"""

    class CustomAgent(BaseAgent):
        role = AgentRole.DEVELOPER

        async def execute(self, input_data: AgentInput) -> AgentOutput:
            return AgentOutput(result={"custom": True})

    AgentFactory.register(AgentRole.DEVELOPER, CustomAgent)
    agent = AgentFactory.get_agent(AgentRole.DEVELOPER)
    assert isinstance(agent, CustomAgent)
    # 恢复
    AgentFactory.register(AgentRole.DEVELOPER, DeveloperAgent)
