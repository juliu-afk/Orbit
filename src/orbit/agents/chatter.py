"""通用对话 Agent（ChatterAgent）——用户首触点。

WHY ChatterAgent: 用户不应每次打开 Orbit 都被 Clarifier 审问需求。
ChatterAgent 无约束、啥都能聊，仅在检测到编程意图时路由到 Clarifier。
其他 Agent (architect/developer/reviewer) 保持原有触发条件不变。

意图路由机制：
- chatter 返回 `output.result` 中包含 `__intent__: "chat"|"programming"`
- task_runner._agent_cycle 检查 intent → "programming" 时继续进入 PARSING
- "chat" 时结束任务（DONE）
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent

logger = structlog.get_logger("orbit.agents.chatter")


CHATTER_SYSTEM_PROMPT = """你是 Orbit 的通用对话助手（ChatterAgent）。你是用户接触 Orbit 的第一个 Agent。

## 你的定位
你是友好、博学、乐于助人的对话伙伴。你不是"需求工程师"或"技术架构师"——
你是一个 AI Agent，你是 Orbit 多智能体系统的一员。你的底层 LLM 由 LiteLLM 网关统一调度。

## 核心能力
- 回答任何问题：技术、生活、学术、闲聊——没有话题限制
- 讨论编程/软件开发（但不过度工程化——保持自然对话）
- 诚实：不知道就说不知道，不编造

## 意图识别规则
当用户表达以下意图时，标记 intent="programming"：
1. 明确的编程任务请求（"写一个..."、"帮我实现..."、"修复这个 bug..."）
2. 软件开发项目规划（"我想做一个..."、"设计一个系统..."）
3. 代码审查/调试请求

普通聊天、问答、讨论（不含具体编程任务）标记 intent="chat"。

## 输出格式
必须返回严格 JSON：
{"reply": "你的回复内容", "intent": "chat", "reason": "简短说明判定理由"}
当 intent="programming" 时，reply 中简要确认用户需求，并告知将转交 Clarifier 做需求澄清。

## 风格
- 轻松、自然、友好
- 可以用表情符号
- 简短回答优于长篇大论（除非用户要求详细）
- 用户问"你是什么模型"时如实回答——你是 Orbit 系统的一部分，底层 LLM 由配置决定
"""


class ChatterAgent(BaseAgent):
    """通用对话 Agent——无约束首触点。

    用法:
        agent = ChatterAgent(llm=llm_client)
        result = await agent.execute(AgentInput(task="今天天气怎么样？"))
    """

    role: AgentRole = AgentRole.CHATTER

    def __init__(self, llm: Any = None, graph: Any = None, sandbox: Any = None) -> None:
        super().__init__(llm=llm, graph=graph, sandbox=sandbox)

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行对话——生成回复 + 意图标记。"""
        if not self.llm:
            return AgentOutput(
                status="ok",
                result={
                    "reply": (
                        "你好！我是 Orbit 的对话助手。当前 LLM 未配置，"
                        "请检查环境变量或 CC_SWITCH 设置。"
                    ),
                    "__intent__": "chat",
                    "reason": "llm_not_configured",
                },
            )

        import json as _json
        import re as _re

        from orbit.gateway.schemas import LLMRequest

        try:
            req = LLMRequest(
                prompt=input_data.task,
                system_prompt=CHATTER_SYSTEM_PROMPT,
                temperature=0.8,
                max_tokens=1024,
            )
            resp = await self.llm.generate(req, task_id=input_data.context.get("task_id", ""))
            content = resp.content or ""

            parsed = self._parse_output(content)
            return AgentOutput(
                status="ok",
                result={
                    "reply": parsed.get("reply", content[:500]),
                    "__intent__": parsed.get("intent", "chat"),
                    "reason": parsed.get("reason", ""),
                },
            )
        except Exception as e:
            logger.warning("chatter_execution_failed", error=str(e))
            return AgentOutput(
                status="ok",
                result={
                    "reply": "抱歉，我暂时无法处理这个消息。请稍后再试。",
                    "__intent__": "chat",
                    "reason": f"error: {e}",
                },
            )

    @staticmethod
    def _parse_output(content: str) -> dict[str, Any]:
        """宽松解析 LLM 返回的 JSON——容错代码块包裹/尾字符/字段缺失。"""
        import json as _json
        import re as _re

        try:
            return _json.loads(content.strip())
        except (_json.JSONDecodeError, ValueError):
            pass

        match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, _re.DOTALL)
        if match:
            try:
                return _json.loads(match.group(1))
            except (_json.JSONDecodeError, ValueError):
                pass

        brace = _re.search(r"\{.*\}", content, _re.DOTALL)
        if brace:
            try:
                return _json.loads(brace.group(0))
            except (_json.JSONDecodeError, ValueError):
                pass

        return {"reply": content.strip(), "intent": "chat", "reason": "parse_fallback"}
