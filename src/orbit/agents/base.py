"""Step 5.2 Agent 基类与数据模型。

WHY 基类：5 个 Agent 共享 execute(input)→output 接口，调度器不关心
具体角色实现，只调用统一接口。依赖注入 LLM/图谱/沙箱，Agent 无状态。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """Agent 角色枚举（PRD 5 角色全覆盖）。"""

    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    QA = "qa"
    CONFIG_MANAGER = "config_manager"
    CLARIFIER = "clarifier"  # 需求澄清 Agent
    DREAM = "dream"  # Phase 2: /dream 自进化 Agent（自然语言交互 PR）
    CHATTER = "chatter"  # 通用对话 Agent——无约束，首触点


class AgentInput(BaseModel):
    """Agent 统一输入模型。

    WHY 统一模型：调度器不关心具体 role 的输入差异，dict 灵活传递。
    """

    task: str = Field(..., min_length=1, description="任务描述")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文（上游节点输出等）")
    role: AgentRole = Field(default=AgentRole.DEVELOPER)


class AgentOutput(BaseModel):
    """Agent 统一输出模型。

    WHY status 字段：调度器据此判断是否需要重试/跳过。
    """

    status: str = "ok"  # ok | error
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BaseAgent(ABC):
    """Agent 基类。

    所有 Agent 必须无状态（不存会话历史），状态由调度器管理。
    LLM/图谱/沙箱通过依赖注入传入，Agent 内部不创建连接。
    """

    role: AgentRole

    def __init__(self, llm: Any = None, graph: Any = None, sandbox: Any = None) -> None:
        self.llm = llm
        self.graph = graph
        self.sandbox = sandbox

    @abstractmethod
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行 Agent 逻辑。"""
        ...

    async def execute_stream(self, input_data: AgentInput, cancel_token: Any = None):
        """流式执行 Agent——async generator（Phase 3）。

        默认实现：调用 execute() 收集结果，包装为单个 FINISH_STEP 事件。
        子类可覆盖为真正的流式实现。

        WHY 检查 cancel_token: 确保非 ReActAgent 子类也能响应取消。
        """
        from orbit.stream.events import StreamEvent, StreamEventType

        # 检查是否在执行前已被取消
        if cancel_token is not None and cancel_token.is_cancelled:
            yield StreamEvent(
                type=StreamEventType.CANCELLED,
                agent_id=self.role.value,
                task_id=input_data.context.get("task_id", ""),
                data={"message": "用户取消"},
            )
            return

        result = await self.execute(input_data)
        yield StreamEvent(
            type=StreamEventType.FINISH_STEP,
            agent_id=self.role.value,
            task_id=input_data.context.get("task_id", ""),
            data={
                "output": result.result.get("output", ""),
                "turns": result.result.get("turns", 1),
                "tool_calls": result.result.get("tool_calls", 0),
            },
        )

    def system_prompt(self) -> str:
        """编排层风格 System Prompt（Step 0.4 架构锚定声明）。"""
        return (
            f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
            "在协作契约约束下工作，输出必须通过 L1-L8 验证。"
            '返回 JSON 格式：{"status": "ok", "result": {...}}'
        )
