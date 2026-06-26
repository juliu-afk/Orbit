"""Step 5.2 AgentFactory + 5 Agent 实现 (Phase 1 升级).

Phase 1 升级：DeveloperAgent/ArchitectAgent/ReviewerAgent/QAAgent → 继承 ReActAgent，
获得 think→act→observe 循环 + 工具调用能力。

ConfigManagerAgent/ClarifierAgent → 保持 BaseAgent（不需要文件工具）。
"""

from __future__ import annotations

import structlog

from orbit.agents.base import AgentRole, BaseAgent
from orbit.agents.clarifier import ClarifierAgent
from orbit.agents.react_agent import ReActAgent

logger = structlog.get_logger()


class ArchitectAgent(ReActAgent):
    """架构师 Agent：系统设计——拥有工具的 ReAct 循环.

    WHY ReActAgent: 架构师需要 read_file/grep/glob 了解现有代码结构，
    再输出设计方案。不再是纯 LLM 输出。
    """

    role = AgentRole.ARCHITECT
    MAX_TURNS = 10  # 设计任务不需要太多轮


class DeveloperAgent(ReActAgent):
    """开发者 Agent：代码实现——完整开发闭环.

    WHY ReActAgent: Developer 是工具最重的 Agent——
    read_file→edit_file→exec_command(pytest)→修复→再测试。
    """

    role = AgentRole.DEVELOPER


class ReviewerAgent(ReActAgent):
    """审查员 Agent：代码质量检查——读取变更后审查.

    WHY ReActAgent: Reviewer 需要 read_file + grep 定位变更，
    不写代码但需要读取上下文。
    """

    role = AgentRole.REVIEWER
    MAX_TURNS = 10  # 审查不需要太多轮


class QAAgent(ReActAgent):
    """QA 验证员 Agent：测试与验证——写测试+跑测试.

    WHY ReActAgent: QA 需要 write_file 写测试文件，
    exec_command 跑 pytest 验证。
    """

    role = AgentRole.QA
    MAX_TURNS = 15  # 测试生成可能需要更多轮


class ConfigManagerAgent(BaseAgent):
    """配置管理员 Agent：环境配置管理.

    WHY BaseAgent 而非 ReActAgent: 配置管理不需要文件操作工具，
    单次 LLM 调用即可完成。
    """

    role = AgentRole.CONFIG_MANAGER

    async def execute(self, input_data):
        from orbit.agents.base import AgentInput, AgentOutput

        if self.llm is None:
            return AgentOutput(result={"config": f"# [mock] config for: {input_data.task}"})
        from orbit.gateway.schemas import LLMRequest

        resp = await self.llm.generate(
            LLMRequest(prompt=input_data.task),
            task_id=input_data.context.get("task_id", ""),
        )
        return AgentOutput(result={"config": resp.content})


class AgentFactory:
    """Agent 工厂——根据角色返回实例。

    WHY 工厂模式：调度器不关心具体 Agent 类，只需调用 get_agent(role)。
    添加新角色不改调度器代码。

    Phase 1 升级：ReActAgent 子类支持 tools + event_bus 注入。
    """

    _registry: dict[AgentRole, type[BaseAgent]] = {
        AgentRole.ARCHITECT: ArchitectAgent,
        AgentRole.DEVELOPER: DeveloperAgent,
        AgentRole.REVIEWER: ReviewerAgent,
        AgentRole.QA: QAAgent,
        AgentRole.CONFIG_MANAGER: ConfigManagerAgent,
        AgentRole.CLARIFIER: ClarifierAgent,
    }

    @classmethod
    def create(
        cls,
        role: AgentRole | str,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
        tools: Any = None,
        event_bus: Any = None,
    ) -> BaseAgent:
        """create = get_agent alias for orchestrator."""
        return cls.get_agent(
            role, llm=llm, graph=graph, sandbox=sandbox,
            tools=tools, event_bus=event_bus,
        )

    @classmethod
    def get_agent(
        cls,
        role: AgentRole | str,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
        tools: Any = None,
        event_bus: Any = None,
    ) -> BaseAgent:
        """按角色创建 Agent 实例。

        Args:
            role: AgentRole 枚举或字符串
            llm: LLMClient 实例（可选，mock 模式不传）
            graph: CodeGraphEngine 实例（可选）
            sandbox: Sandbox 实例（可选）
            tools: ToolRegistry 实例（Phase 1——供 ReActAgent 使用）
            event_bus: EventBus 实例（Phase 1——供实时事件推送）

        Returns:
            对应角色的 BaseAgent 实例

        Raises:
            ValueError: 未知角色
        """
        if isinstance(role, str):
            role = AgentRole(role)
        agent_cls = cls._registry.get(role)
        if agent_cls is None:
            raise ValueError(f"Unknown agent role: {role}")

        # Phase 1: ReActAgent 子类需要 tools + event_bus
        if issubclass(agent_cls, ReActAgent):
            return agent_cls(
                llm=llm, graph=graph, sandbox=sandbox,
                tools=tools, event_bus=event_bus,
            )
        return agent_cls(llm=llm, graph=graph, sandbox=sandbox)

    @classmethod
    def register(cls, role: AgentRole, agent_cls: type[BaseAgent]) -> None:
        """注册新 Agent（扩展用）。"""
        cls._registry[role] = agent_cls
