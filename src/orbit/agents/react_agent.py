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
        # Phase 2: 压缩管线——子类或外部可注入
        self._compressor: Any = None
        self._budget_tracker: Any = None

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """ReAct 循环主入口——每步实时推送到事件总线（非黑盒）。

        对标 OpenCode runLoop():
        while turn < MAX_TURNS:
            1. LLM 思考 (think)
            2. 判断退出条件
            3. 执行工具 (act)
            4. 结果反馈 (observe)
        """
        from orbit.prompt.builder import PromptBuilder

        task_id = input_data.context.get("task_id", "react")

        # 1. 构建 system prompt——三层拼接
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

        # 3. ReAct 循环
        for turn in range(self.MAX_TURNS):
            # 3a. 推送 turn_start 事件
            await self._emit(
                task_id,
                "agent.turn_start",
                {
                    "turn": turn,
                    "agent": self.role.value,
                    "remaining_turns": self.MAX_TURNS - turn,
                },
            )

            # 3a+. Phase 2: 上下文压缩——每轮 LLM 调用前检查 token 用量
            if self._compressor and self._budget_tracker:
                try:
                    from orbit.compression.models import CompressionAction

                    result = await self._compressor.compress(
                        messages,
                        task_id=task_id,
                        turn=turn,
                    )
                    if result.action == CompressionAction.FORK:
                        await self._emit(
                            task_id,
                            "agent.context_fork",
                            {
                                "turn": turn,
                                "child_session_id": result.child_session_id,
                            },
                        )
                        return AgentOutput(
                            status="ok",
                            result={
                                "output": "上下文过大，已在子 Session 中继续。",
                                "child_session_id": result.child_session_id,
                                "reasoning_chain": reasoning_chain,
                                "turns": turn + 1,
                                "tool_calls": tool_call_count,
                            },
                        )
                    if result.action != CompressionAction.SKIP:
                        await self._emit(
                            task_id,
                            "agent.compression",
                            {
                                "turn": turn,
                                "action": result.action,
                                "original_tokens": result.original_tokens,
                                "compressed_tokens": result.compressed_tokens,
                                "ratio": result.ratio,
                                "layers": result.layers_applied,
                            },
                        )
                except Exception as e:
                    logger.warning("compression_hook_failed", error=str(e))

            # 3b. LLM 思考
            if self.llm is None:
                # mock 模式——无 LLM，直接返回
                return AgentOutput(
                    status="ok",
                    result={
                        "note": "[mock] ReAct 循环跳过——无 LLM 连接",
                        "task": input_data.task[:200],
                        "turns": 1,
                        "tool_calls": 0,
                    },
                )

            req = LLMRequest(
                prompt=input_data.task,
                system_prompt=system,
                messages=messages if len(messages) > 2 else None,
                tools=tools_schema if tools_schema else None,
            )
            response = await self.llm.generate(req, task_id=task_id)

            # 3c. 判断退出条件
            stop_reason = response.stop_reason

            # AC8: 正常完成
            if stop_reason == "end_turn":
                reasoning_chain.append(
                    {
                        "turn": turn,
                        "action": "finish",
                        "reasoning": response.content[:500] if response.content else "",
                    }
                )
                await self._emit(
                    task_id,
                    "agent.turn_end",
                    {
                        "turn": turn,
                        "action": "complete",
                    },
                )
                return AgentOutput(
                    status="ok",
                    result={
                        "output": response.content,
                        "reasoning_chain": reasoning_chain,
                        "turns": turn + 1,
                        "tool_calls": tool_call_count,
                    },
                )

            # AC8: token 截断
            if stop_reason == "max_tokens":
                reasoning_chain.append(
                    {
                        "turn": turn,
                        "action": "truncated",
                        "reasoning": response.content[:500] if response.content else "",
                    }
                )
                logger.warning("react_max_tokens", turn=turn, task_id=task_id)
                # 附加截断前的内容并返回
                return AgentOutput(
                    status="ok",
                    result={
                        "output": response.content,
                        "warning": "达到 token 上限，输出已截断",
                        "reasoning_chain": reasoning_chain,
                        "turns": turn + 1,
                        "tool_calls": tool_call_count,
                    },
                )

            # AC8: 权限阻断 / 错误
            if stop_reason == "error":
                return AgentOutput(
                    status="error",
                    error=response.content or "LLM 返回错误",
                    result={"reasoning_chain": reasoning_chain},
                )

            # 3d. 执行工具调用
            if stop_reason == "tool_calls" and response.tool_calls:
                for tc in response.tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    tool_args_str = func.get("arguments", "{}")

                    # 解析参数 JSON
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {"raw": tool_args_str}

                    # 3e. Doom Loop 检测 (AC5)——前置检测，避免第3次白白执行
                    agent_key = f"{self.role.value}_{task_id}"
                    if self.tools.would_form_loop(agent_key, tool_name, tool_args):
                        logger.warning(
                            "doom_loop_detected",
                            agent=self.role.value,
                            tool=tool_name,
                        )
                        await self._emit(
                            task_id,
                            "agent.doom_loop_warn",
                            {
                                "tool": tool_name,
                                "args": tool_args,
                                "turn": turn,
                            },
                        )
                        # 推送到消息历史——让 LLM 知道被阻止了
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": (
                                    f"⚠ 死循环检测——连续 3 次调用 {tool_name} 相同参数。"
                                    "请换一种方式完成任务或报告无法继续。"
                                ),
                            }
                        )
                        continue

                    # 3f. 记录工具调用（检测通过后才记录）
                    self.tools.record_tool_call(agent_key, tool_name, tool_args)

                    # 3g. 推送 tool_call_start 事件
                    await self._emit(
                        task_id,
                        "agent.tool_call_start",
                        {
                            "tool": tool_name,
                            "args": {
                                k: (str(v)[:100] if isinstance(v, str) else v)
                                for k, v in tool_args.items()
                            },
                            "turn": turn,
                        },
                    )

                    # 3h. 执行工具——传递 agent_name 供审计
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
                        logger.error(
                            "tool_exec_error",
                            tool=tool_name,
                            error=str(e),
                        )

                    # 3i. 截断输出 (AC6b)
                    truncated = _truncate_output(result_str, MAX_RESULT_CHARS)

                    # 3j. 记录推理链
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

                    # 3k. 反馈结果到消息历史
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tc],
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": truncated,
                        }
                    )

                    # 3l. 推送 tool_call_end 事件
                    await self._emit(
                        task_id,
                        "agent.tool_call_end",
                        {
                            "tool": tool_name,
                            "result_size": len(result_str),
                            "truncated": len(result_str) > MAX_RESULT_CHARS,
                        },
                    )

                    tool_call_count += 1
                    self._budget.consume()

                continue  # ← 回到 3a，下一轮 LLM 思考

        # 4. AC8: 步数上限
        logger.warning("react_max_turns", turns=self.MAX_TURNS, task_id=task_id)
        return AgentOutput(
            status="error",
            error=f"超过最大轮数 ({self.MAX_TURNS})——任务未完成",
            result={
                "reasoning_chain": reasoning_chain,
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
