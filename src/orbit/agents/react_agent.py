"""ReActAgent 基类——think→act→observe 循环.

对标: OpenCode prompt.ts:1400 runLoop()
     + Claude Code while loop + tool_calls
     + Hermes conversation_loop.py:496

WHY ReAct 而非单次 LLM 调用:
  单次调用只能输出文本，不能读文件/写代码/跑测试。
  ReAct 循环让 Agent 真正干活——观察→思考→行动→验证。
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, BaseAgent
from orbit.events.schemas import DashboardEvent
from orbit.gateway.schemas import LLMRequest
from orbit.stream.cancellation import CancellationToken
from orbit.stream.events import StreamEvent, StreamEventType
from orbit.tools.registry import DoomLoopError, ToolRegistry

logger = structlog.get_logger()

# 最大 tool call 结果长度（截断前）
MAX_RESULT_CHARS = 10000


class IterationBudget:
    """迭代预算——对标 Hermes iteration_budget.

    WHY 独立类: 预算消耗逻辑与循环逻辑分离，方便测试。
    """

    def __init__(self, total: int = 90) -> None:
        self.total = total
        self._consumed = 0

    def consume(self, n: int = 1) -> bool:
        """消耗 n 个预算单位。返回是否还有剩余。"""
        self._consumed += n
        return self._consumed <= self.total

    @property
    def remaining(self) -> int:
        return max(0, self.total - self._consumed)


class ReActAgent(BaseAgent):
    """ReAct 循环基类——think→act→observe.

    子类只需覆盖 role 和 system_prompt()，
    execute() 继承自动获得 ReAct 循环能力。

    Usage:
        class DeveloperAgent(ReActAgent):
            role = AgentRole.DEVELOPER
    """

    MAX_TURNS = 20
    ITERATION_BUDGET = 90  # 对标 Hermes max_iterations

    # Phase 2: 压缩管线（类级默认——子类通过 __init__ 注入）
    _compressor: Any = None
    _budget_tracker: Any = None

    def __init__(
        self,
        llm: Any = None,
        graph: Any = None,
        sandbox: Any = None,
        tools: ToolRegistry | None = None,
        event_bus: Any = None,
    ) -> None:
        super().__init__(llm=llm, graph=graph, sandbox=sandbox)
        self.tools = tools or ToolRegistry.get_instance()
        self._event_bus = event_bus
        self._budget = IterationBudget(self.ITERATION_BUDGET)

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """ReAct 循环主入口——向后兼容 wrapper。

        Phase 3 重构：内部委托给 execute_stream()，收集流式事件后组装 AgentOutput。
        旧调用方（orchestrator/clarifier）无需改动。
        """
        reasoning_chain: list[dict] = []
        output_text = ""
        turns = 0
        tool_call_count = 0

        async for event in self.execute_stream(input_data):
            # 从 FINISH_STEP/ERROR/CANCELLED 事件中提取 reasoning_chain（始终是最新的）
            event_chain = event.data.get("reasoning_chain")
            if event_chain is not None:
                reasoning_chain = event_chain

            if event.type == StreamEventType.FINISH_STEP:
                output_text = event.data.get("output", "")
                turns = event.data.get("turns", 0)
                tool_call_count = event.data.get("tool_calls", 0)
                return AgentOutput(
                    status="ok",
                    result={
                        "output": output_text,
                        "reasoning_chain": reasoning_chain,
                        "turns": turns,
                        "tool_calls": tool_call_count,
                        "child_session_id": event.data.get("child_session_id"),
                    },
                )

            elif event.type == StreamEventType.CANCELLED:
                return AgentOutput(
                    status="error",
                    error="用户取消",
                    result={
                        "reasoning_chain": reasoning_chain,
                        "turns": event.turn,
                        "tool_calls": tool_call_count,
                    },
                )

            elif event.type == StreamEventType.ERROR:
                return AgentOutput(
                    status="error",
                    error=event.data.get("message", "未知错误"),
                    result={
                        "reasoning_chain": reasoning_chain,
                        "code": event.data.get("code", "UNKNOWN"),
                    },
                )

        # 流式正常结束但无 FINISH_STEP（不应发生）
        return AgentOutput(
            status="ok",
            result={
                "output": output_text,
                "reasoning_chain": reasoning_chain,
                "turns": turns,
                "tool_calls": tool_call_count,
            },
        )

    async def execute_stream(
        self, input_data: AgentInput, cancel_token: CancellationToken | None = None
    ):
        """流式 ReAct 循环——async generator（Phase 3 AC19）。

        对标 OpenCode runLoop 事件模型：
        while turn < MAX_TURNS:
            yield TURN_START → yield TEXT_DELTA (逐 token) → yield TOOL_CALL → yield TOOL_RESULT
        → yield FINISH_STEP

        旧 execute() 内部调用此方法收集结果——保持向后兼容。
        """
        from orbit.prompt.builder import PromptBuilder

        task_id = input_data.context.get("task_id", "react")
        agent_id = self.role.value

        # 1. 构建 system prompt
        prompt_builder = PromptBuilder()
        system = prompt_builder.build(
            role=self.role,
            context=input_data.context,
            tools_schema=self.tools.get_schemas(),
        )

        # 2. 初始化消息历史
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": input_data.task},
        ]
        tools_schema = self.tools.get_schemas()
        reasoning_chain: list[dict] = []
        tool_call_count = 0

        # 3. ReAct 循环（streaming 版本）
        for turn in range(self.MAX_TURNS):
            # 3a. 检查取消信号（用户中断）
            if cancel_token and cancel_token.is_cancelled:
                yield StreamEvent(
                    type=StreamEventType.CANCELLED,
                    agent_id=agent_id,
                    task_id=task_id,
                    turn=turn,
                    data={"message": "用户取消"},
                )
                return

            # 3b. yield TURN_START
            yield StreamEvent(
                type=StreamEventType.TURN_START,
                agent_id=agent_id,
                task_id=task_id,
                turn=turn,
                data={"turn": turn, "remaining_turns": self.MAX_TURNS - turn},
            )

            # 3c. Phase 2: 上下文压缩
            if self._compressor and self._budget_tracker:
                try:
                    from orbit.compression.models import CompressionAction

                    result = await self._compressor.compress(
                        messages,
                        task_id=task_id,
                        turn=turn,
                    )
                    if result.action == CompressionAction.FORK:
                        yield StreamEvent(
                            type=StreamEventType.FINISH_STEP,
                            agent_id=agent_id,
                            task_id=task_id,
                            turn=turn,
                            data={
                                "output": "上下文过大，已在子 Session 中继续。",
                                "child_session_id": result.child_session_id,
                                "turns": turn + 1,
                                "tool_calls": tool_call_count,
                            },
                        )
                        return
                except Exception as e:
                    logger.warning("compression_hook_failed", error=str(e))

            # 3d. 检查 mock 模式
            if self.llm is None:
                yield StreamEvent(
                    type=StreamEventType.FINISH_STEP,
                    agent_id=agent_id,
                    task_id=task_id,
                    turn=turn,
                    data={
                        "output": "[mock] ReAct 循环跳过——无 LLM 连接",
                        "task": input_data.task[:200],
                        "turns": 1,
                        "tool_calls": 0,
                    },
                )
                return

            # 3e. LLM 流式调用
            req = LLMRequest(
                prompt=input_data.task,
                system_prompt=system,
                messages=messages if len(messages) > 2 else None,
                tools=tools_schema if tools_schema else None,
            )

            # 流式接收 text_delta + tool_call
            has_tool_calls = False
            content_parts: list[str] = []
            try:
                async for event_type, event_data in self.llm.generate_stream_with_tools(
                    req,
                    task_id=task_id,
                    agent_name=agent_id,
                ):
                    if event_type == StreamEventType.TEXT_DELTA:
                        content_parts.append(event_data["delta"])
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA,
                            agent_id=agent_id,
                            task_id=task_id,
                            turn=turn,
                            data=event_data,
                        )

                    elif event_type == StreamEventType.TOOL_CALL:
                        has_tool_calls = True
                        tool_calls = event_data.get("tool_calls", [])

                        # 推送 TOOL_CALL 事件
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL,
                            agent_id=agent_id,
                            task_id=task_id,
                            turn=turn,
                            data={"tool_calls": tool_calls},
                        )

                        # 执行每个工具
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            tool_name = func.get("name", "")
                            tool_args_str = func.get("arguments", "{}")

                            try:
                                tool_args = json.loads(tool_args_str)
                            except json.JSONDecodeError:
                                tool_args = {"raw": tool_args_str}

                            # Doom Loop 检测——警告但不阻塞（非致命错误）
                            agent_key = f"{self.role.value}_{task_id}"
                            if self.tools.would_form_loop(agent_key, tool_name, tool_args):
                                logger.warning(
                                    "doom_loop_detected",
                                    agent=self.role.value,
                                    tool=tool_name,
                                )
                                # 注入完整消息对到历史——assistant(tool_calls) + tool(warning)
                                # WHY 必须先 assistant: 否则 provider 拒绝孤儿 tool 消息
                                messages.append(
                                    {"role": "assistant", "content": None, "tool_calls": [tc]}
                                )
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc.get("id", ""),
                                        "content": f"死循环检测——连续3次调用 {tool_name} 相同参数。请换一种方式完成任务或报告无法继续。",
                                    }
                                )
                                continue

                            self.tools.record_tool_call(agent_key, tool_name, tool_args)

                            try:
                                result_str = await self.tools.dispatch(
                                    tool_name,
                                    tool_args,
                                    agent_name=self.role.value,
                                )
                            except DoomLoopError:
                                result_str = "检测到工具调用死循环，请换一种方式。"
                            except Exception as e:
                                result_str = f"工具执行失败: {str(e)}"

                            truncated = _truncate_output(result_str, MAX_RESULT_CHARS)

                            # 推送 TOOL_RESULT
                            yield StreamEvent(
                                type=StreamEventType.TOOL_RESULT,
                                agent_id=agent_id,
                                task_id=task_id,
                                turn=turn,
                                data={
                                    "tool": tool_name,
                                    "result_size": len(result_str),
                                    "truncated": len(result_str) > MAX_RESULT_CHARS,
                                    "result_preview": truncated[:200],
                                },
                            )

                            # 更新消息历史
                            messages.append(
                                {"role": "assistant", "content": None, "tool_calls": [tc]}
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.get("id", ""),
                                    "content": truncated,
                                }
                            )

                            # 推理链记录
                            reasoning_chain.append(
                                {
                                    "turn": turn,
                                    "action": tool_name,
                                    "args": {
                                        k: (str(v)[:100] if isinstance(v, str) else v)
                                        for k, v in tool_args.items()
                                    },
                                    "result_preview": truncated[:200],
                                }
                            )

                            tool_call_count += 1
                            self._budget.consume()

                    elif event_type == StreamEventType.ERROR:
                        yield StreamEvent(
                            type=StreamEventType.ERROR,
                            agent_id=agent_id,
                            task_id=task_id,
                            turn=turn,
                            data=event_data,
                        )
                        return

            except Exception as e:
                logger.error("stream_error", error=str(e), task_id=task_id)
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    agent_id=agent_id,
                    task_id=task_id,
                    turn=turn,
                    data={"message": str(e), "code": "LLM_ERROR"},
                )
                return

            # 3f. 无 tool_calls → 正常完成
            if not has_tool_calls:
                reasoning_chain.append(
                    {
                        "turn": turn,
                        "action": "finish",
                        "reasoning": "".join(content_parts)[:500],
                    }
                )
                yield StreamEvent(
                    type=StreamEventType.FINISH_STEP,
                    agent_id=agent_id,
                    task_id=task_id,
                    turn=turn,
                    data={
                        "output": "".join(content_parts),
                        "reasoning_chain": reasoning_chain,
                        "turns": turn + 1,
                        "tool_calls": tool_call_count,
                    },
                )
                return

        # 4. 步数上限
        logger.warning("react_max_turns", turns=self.MAX_TURNS, task_id=task_id)
        yield StreamEvent(
            type=StreamEventType.ERROR,
            agent_id=agent_id,
            task_id=task_id,
            turn=self.MAX_TURNS,
            data={
                "message": f"超过最大轮数 ({self.MAX_TURNS})——任务未完成",
                "code": "MAX_TURNS",
                "turns": self.MAX_TURNS,
                "tool_calls": tool_call_count,
            },
        )

    # ── 内部 ─────────────────────────────────────────────

    async def _emit(self, task_id: str, event_type: str, data: dict) -> None:
        """推送事件到 EventBus——对标 OpenCode fullStream events。

        非阻塞——事件丢失不影响 Agent 逻辑。
        """
        if not self._event_bus:
            return
        try:
            event = DashboardEvent(
                type=event_type,
                task_id=task_id,
                payload=data,
            )
            self._event_bus.publish(event)
        except Exception:
            pass  # 驾驶舱事件丢失不阻塞 Agent


# ── 模块级函数 ─────────────────────────────────────────


def _truncate_output(text: str, max_chars: int = MAX_RESULT_CHARS) -> str:
    """截断超长输出——头尾 + 摘要。对标 Claude Code Tool Output Truncation。"""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    cut = len(text) - max_chars
    return text[:half] + f"\n\n... [截断 {cut} 字符] ...\n\n" + text[-half:]
