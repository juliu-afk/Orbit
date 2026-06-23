"""Step 5.2 AgentFactory + 5 Agent 实现。

WHY 单文件而非 5 文件：每个 Agent MVP 阶段是轻量 Prompt 包装器，
核心差异在 System Prompt 和输出解析。过早拆文件增加维护成本。
Step 5.x 各 Agent 逻辑复杂化后可拆分。
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent

logger = structlog.get_logger()


class ArchitectAgent(BaseAgent):
    """架构师 Agent：系统设计。

    WHY 职责分离：架构师只做高层设计（组件/数据流/技术选型），
    不写代码。设计结果供 Developer Agent 消费。
    """

    role = AgentRole.ARCHITECT

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        prompt = self._build_prompt(input_data.task, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"design": f"[mock] 架构设计: {input_data.task}"})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"design": resp.content})

    def _build_prompt(self, task: str, context: dict[str, Any]) -> str:
        return f"""基于以下需求设计系统架构：

需求：{task}
上下文：{json.dumps(context, ensure_ascii=False)}

输出要求：
1. 组件列表（模块/类）
2. 数据流描述
3. 技术选型建议
"""

    def system_prompt(self) -> str:
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "专注于系统架构设计，输出结构化的设计文档。"
        )


class DeveloperAgent(BaseAgent):
    """开发者 Agent：代码实现。

    WHY 职责分离：Developer 接收架构师的设计，输出可执行代码。
    不负责测试（QA Agent）和审查（Reviewer Agent）。
    """

    role = AgentRole.DEVELOPER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        design = input_data.context.get("design", input_data.task)
        prompt = self._build_prompt(design, input_data.context)
        if self.llm is None:
            return AgentOutput(
                result={"code": f"# [mock] code for: {input_data.task}", "language": "python"}
            )
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"code": resp.content, "language": "python"})

    def _build_prompt(self, design: str, context: dict[str, Any]) -> str:
        code_context = context.get("code_context", "")
        return f"""基于设计方案生成代码：

设计：{design}
代码上下文（已有代码）：{code_context}

输出可直接运行的 Python 代码，包含函数定义和类型注解。
"""

    def system_prompt(self) -> str:
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "专注于编写高质量 Python 代码，严格类型注解，符合 PEP 规范。"
        )


class ReviewerAgent(BaseAgent):
    """审查员 Agent：代码质量检查。

    WHY 职责分离：独立审查避免 Developer 自审盲区。
    """

    role = AgentRole.REVIEWER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        code = input_data.context.get("code", input_data.task)
        prompt = self._build_prompt(code, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"review": "[mock] 审查通过", "issues": []})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"review": resp.content, "issues": []})

    def _build_prompt(self, code: str, context: dict[str, Any]) -> str:
        return f"""审查以下代码的质量和安全性：

代码：
{code}

检查项：类型注解、异常处理、SQL注入、命令注入、空值处理、逻辑错误。
输出格式：逐条列出问题（严重/一般），无问题则写"审查通过"。
"""

    def system_prompt(self) -> str:
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "专注于代码审查，发现潜在缺陷、安全隐患、性能问题。"
        )


class QAAgent(BaseAgent):
    """QA 验证员 Agent：测试与验证。

    WHY 职责分离：QA 独立编写测试用例，与 Developer 形成双人开发模式。
    """

    role = AgentRole.QA

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        code = input_data.context.get("code", input_data.task)
        prompt = self._build_prompt(code, input_data.context)
        if self.llm is None:
            return AgentOutput(
                result={"tests": f"# [mock] tests for: {input_data.task}", "passed": True}
            )
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"tests": resp.content, "passed": True})

    def _build_prompt(self, code: str, context: dict[str, Any]) -> str:
        return f"""为以下代码生成 pytest 测试用例：

代码：
{code}

要求：覆盖正常路径和异常情况，使用 pytest 风格。
"""

    def system_prompt(self) -> str:
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "专注于测试用例生成，覆盖边界和异常场景。"
        )


class ConfigManagerAgent(BaseAgent):
    """配置管理员 Agent：环境配置管理。

    WHY 职责分离：配置漂移检测（L8）需要 Agent 主动管理配置文件，
    而不是被动告警。
    """

    role = AgentRole.CONFIG_MANAGER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        prompt = self._build_prompt(input_data.task, input_data.context)
        if self.llm is None:
            return AgentOutput(result={"config": f"# [mock] config for: {input_data.task}"})
        resp = await self.llm.generate(prompt, task_id=input_data.context.get("task_id", ""))
        return AgentOutput(result={"config": resp.content})

    def _build_prompt(self, task: str, context: dict[str, Any]) -> str:
        return f"""管理以下环境配置：

任务：{task}
当前环境变量：{json.dumps(context.get('env', {}), ensure_ascii=False)}

输出配置变更建议或执行配置更新。
"""

    def system_prompt(self) -> str:
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "专注于环境配置管理，确保配置一致性。"
        )


class AgentFactory:
    """Agent 工厂：根据角色返回实例。

    WHY 工厂模式：调度器不关心具体 Agent 类，只需调用 get_agent(role)。
    添加新角色不改调度器代码。
    """

    _registry: dict[AgentRole, type[BaseAgent]] = {
        AgentRole.ARCHITECT: ArchitectAgent,
        AgentRole.DEVELOPER: DeveloperAgent,
        AgentRole.REVIEWER: ReviewerAgent,
        AgentRole.QA: QAAgent,
        AgentRole.CONFIG_MANAGER: ConfigManagerAgent,
    }

    @classmethod
    def get_agent(
        cls,
        role: AgentRole | str,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
    ) -> BaseAgent:
        """按角色创建 Agent 实例。

        Args:
            role: AgentRole 枚举或字符串
            llm: LLMClient 实例（可选，mock 模式不传）
            graph: CodeGraphEngine 实例（可选）
            sandbox: Sandbox 实例（可选）

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
        return agent_cls(llm=llm, graph=graph, sandbox=sandbox)

    @classmethod
    def register(cls, role: AgentRole, agent_cls: type[BaseAgent]) -> None:
        """注册新 Agent（扩展用）。"""
        cls._registry[role] = agent_cls
