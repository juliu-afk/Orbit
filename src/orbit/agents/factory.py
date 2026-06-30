"""Step 5.2 AgentFactory + 5 Agent 实现 (Phase 1 升级).

Phase 1 升级：DeveloperAgent/ArchitectAgent/ReviewerAgent/QAAgent → 继承 ReActAgent，
获得 think→act→observe 循环 + 工具调用能力。

ConfigManagerAgent/ClarifierAgent → 保持 BaseAgent（不需要文件工具）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.compression.budget import TokenBudgetTracker
    from orbit.compression.compressor import ContextCompressor
    from orbit.events.bus import EventBus
    from orbit.gateway.client import LLMClient
    from orbit.goal_judge.judge import GoalJudge
    from orbit.goal_judge.models import Goal
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.sandbox.executor import Sandbox
    from orbit.tools.registry import ToolRegistry

import structlog

from orbit.agents.base import AgentRole, BaseAgent
from orbit.agents.clarifier import ClarifierAgent
from orbit.agents.dream_agent import DreamAgent
from orbit.agents.react_agent import ReActAgent
from orbit.knowledge.templates import get_registry

logger = structlog.get_logger()


def _build_templates_prompt(task_keywords: list[str] | None) -> str:
    """从模板库匹配模板，返回可注入 system_prompt 的文本块.

    WHY 独立函数: Architect 和 Developer 的 system_prompt() 复用同一套匹配逻辑。
    匹配分数 > 0.5 的模板会被注入，无匹配时返回空字符串（提示不变）。
    """
    if not task_keywords:
        return ""
    try:
        text = get_registry().match_and_format(task_keywords, threshold=0.5)
        if not text:
            return ""
        return "\n\n## 优先使用以下已验证模板\n\n" + text
    except Exception:
        logger.exception("模板匹配失败，跳过模板注入")
        return ""


class ArchitectAgent(ReActAgent):
    """架构师 Agent：系统设计——拥有工具的 ReAct 循环.

    WHY ReActAgent: 架构师需要 read_file/grep/glob 了解现有代码结构，
    再输出设计方案。不再是纯 LLM 输出。

    Phase 2: 多视角方案生成——强制输出 ≥2 个备选方案并评分。
    """

    role = AgentRole.ARCHITECT
    MAX_TURNS = 10  # 设计任务不需要太多轮

    def system_prompt(self) -> str:
        """多视角架构师提示——CARO 风格结构化思维.

        WHY 覆盖基类: 标准 prompt 只要求输出 JSON，不要求多方案。
        多视角降低单方案"隧道效应"风险。
        """
        base = super().system_prompt()
        extra = """## 设计方法论
作为架构师，对每个设计任务必须：
1. **问题类型判断**：这是 CRUD / 算法 / 集成 / 重构 中的哪一类？
2. **相似经验回忆**：项目中是否有类似问题的已有实现？如有，标注参考。
3. **多方案生成**：生成至少 2 个互斥的备选方案（不同架构模式、不同技术栈、不同粒度）
4. **三维评分**：对每个方案从 [可行性/可维护性/性能] 三个维度打分（0-10），选最优
5. **最优方案详述**：对最高分方案详细说明接口设计、数据流、需改动的文件"""
        tmpl_block = _build_templates_prompt(self._task_keywords)
        return f"{base}\n\n{extra}{tmpl_block}"


class DeveloperAgent(ReActAgent):
    """开发者 Agent：代码实现——完整开发闭环.

    WHY ReActAgent: Developer 是工具最重的 Agent——
    read_file→edit_file→exec_command(pytest)→修复→再测试。
    """

    role = AgentRole.DEVELOPER

    def system_prompt(self) -> str:
        """开发者提示——含模板参考（如有匹配）.

        WHY 覆盖基类: 注入匹配的代码模板，减少低级格式错误的反复迭代。
        """
        base = super().system_prompt()
        tmpl_block = _build_templates_prompt(self._task_keywords)
        return f"{base}{tmpl_block}"


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

    async def system_prompt(self) -> str:
        prompt = await super().system_prompt()
        # 减熵闭环-3 B7: 测试覆盖空洞检测
        prompt += (
            "\n## 测试覆盖空洞分析\n"
            "生成测试前，先分析目标函数的参数类型与已有测试的输入值组合，"
            "找出未覆盖的边界条件（如 None/空值/负数/超限值），优先补洞。\n"
        )
        return prompt


class ConfigManagerAgent(BaseAgent):
    """配置管理员 Agent：环境配置管理.

    WHY BaseAgent 而非 ReActAgent: 配置管理不需要文件操作工具，
    单次 LLM 调用即可完成。
    """

    role = AgentRole.CONFIG_MANAGER

    async def execute(self, input_data):
        from orbit.agents.base import AgentOutput

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
        AgentRole.DREAM: DreamAgent,  # Phase 2: /dream 自进化
    }

    @classmethod
    def create(
        cls,
        role: AgentRole | str,
        llm: LLMClient | None = None,
        graph: CodeGraphEngine | None = None,
        sandbox: Sandbox | None = None,
        tools: ToolRegistry | None = None,
        event_bus: EventBus | None = None,
        compressor: ContextCompressor | None = None,  # Phase 2 AC7
        budget_tracker: TokenBudgetTracker | None = None,  # Phase 2 AC7
        task_keywords: list[str] | None = None,  # 模板匹配关键词
        goal: Goal | None = None,  # Phase 4 AC-B1: Goal
        goal_judge: GoalJudge | None = None,  # Phase 4 AC-B1: GoalJudge
    ) -> BaseAgent:
        """create = get_agent alias for orchestrator."""
        return cls.get_agent(
            role,
            llm=llm,
            graph=graph,
            sandbox=sandbox,
            tools=tools,
            event_bus=event_bus,
            goal=goal,
            goal_judge=goal_judge,
            compressor=compressor,
            budget_tracker=budget_tracker,
            task_keywords=task_keywords,
        )

    @classmethod
    def get_agent(
        cls,
        role: AgentRole | str,
        llm: LLMClient | None = None,
        graph: CodeGraphEngine | None = None,
        sandbox: Sandbox | None = None,
        tools: ToolRegistry | None = None,
        event_bus: EventBus | None = None,
        goal: Goal | None = None,  # Phase 4 AC-B1: Goal
        goal_judge: GoalJudge | None = None,  # Phase 4 AC-B1: GoalJudge
        compressor: ContextCompressor | None = None,  # Phase 2 AC7
        budget_tracker: TokenBudgetTracker | None = None,  # Phase 2 AC7
        task_keywords: list[str] | None = None,  # 模板匹配关键词
    ) -> BaseAgent:
        """按角色创建 Agent 实例。

        Args:
            role: AgentRole 枚举或字符串
            llm: LLMClient 实例（可选，mock 模式不传）
            graph: CodeGraphEngine 实例（可选）
            sandbox: Sandbox 实例（可选）
            tools: ToolRegistry 实例（供 ReActAgent 使用）
            event_bus: EventBus 实例（供实时事件推送）
            goal: Goal 模型（Phase 4——GoalJudge 判定用）
            goal_judge: GoalJudge 实例（Phase 4——每轮 turn 后自检）
            task_keywords: 任务关键词列表（供模板库匹配注入 system_prompt）

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

        if issubclass(agent_cls, ReActAgent):
            return agent_cls(
                llm=llm,
                graph=graph,
                sandbox=sandbox,
                tools=tools,
                event_bus=event_bus,
                goal=goal,
                goal_judge=goal_judge,
                role=role,  # Issue #3: 显式传递 role，消除 spawn.py type: ignore
                compressor=compressor,  # Phase 2 AC7
                budget_tracker=budget_tracker,  # Phase 2 AC7
                task_keywords=task_keywords,  # 模板匹配关键词
            )
        return agent_cls(llm=llm, graph=graph, sandbox=sandbox)

    @classmethod
    def register(cls, role: AgentRole, agent_cls: type[BaseAgent]) -> None:
        """注册新 Agent（扩展用）。"""
        cls._registry[role] = agent_cls
