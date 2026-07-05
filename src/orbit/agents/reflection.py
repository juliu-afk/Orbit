"""ReflAct Reflection 阶段——在 ReAct 循环中插入自我反思。

WHY ReflAct:
  ReAct 的经典失败模式——Agent 在行动中逐渐漂移目标而自察不到。
  在每个 Observation 之后插入 Reflection 阶段，让 Agent 成为自身的观察者。

对标: AgentDebug (UIUC+Stanford+AMD), ReflAct (2025), StateAct (2025)

插入点: react_agent.py execute_stream() 中 GoalJudge 之前 (line 453)
  for turn in range(MAX_TURNS):
      LLM generate_stream_with_tools()
      for TOOL_CALL: dispatch + yield TOOL_RESULT
      [REFLECTION ← NEW] 结构化反思 Prompt → LLM 调用 → 解析 JSON
      GoalJudge self-check (existing)
      if no tool_calls: finish
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

import structlog

logger = structlog.get_logger("orbit.agents.reflection")

# 轻量 Reflection Prompt——每个 Action+Observation 后运行
# 输出结构化 JSON，主循环解析后决定继续/调整/停止
REFLECTION_PROMPT = """## Reflection Phase——评估当前步骤是否对准目标

### 原始目标
{original_goal}

### 当前步骤
- 上一步思考 (Thought): {last_thought}
- 执行的动作 (Action): {last_action}
- 观察结果 (Observation): {last_observation}

### 评估问题（逐条回答）:
1. **目标对齐** (Goal Alignment): 这个 Observation 让我更接近原始目标了吗？(YES / NO / PARTIALLY)
2. **新信息** (New Information): 我现在拥有什么之前没有的信息？
3. **下一步方向** (Next Direction): 基于 Observation，下一步应该做什么？
4. **置信度** (Confidence): 我有多确信自己还在正确的轨道上？(0-100)

请以 JSON 格式回复（不要 Markdown 代码块，只要 JSON）:
{{"goal_alignment": "YES", "new_information": "...", "next_direction": "...", "confidence": 80, "should_continue": true, "correction_needed": null}}"""

# 最小 Prompt——只检查目标对齐，不做深度反思。用于轻量快速场景。
REFLECTION_PROMPT_QUICK = """## Quick Reflection

Goal: {original_goal}
Last Action: {last_action}
Observation: {last_observation}

Did this bring me closer to the goal? Answer YES/NO/PARTIALLY and explain why in one sentence.
Respond JSON: {{"goal_alignment": "YES", "reason": "..."}}"""


class ReflectionResult:
    """Reflection 阶段的结构化输出。"""

    def __init__(
        self,
        goal_alignment: str = "YES",
        new_information: str = "",
        next_direction: str = "",
        confidence: int = 80,
        should_continue: bool = True,
        correction_needed: str | None = None,
        raw_json: dict | None = None,
    ) -> None:
        self.goal_alignment = goal_alignment
        self.new_information = new_information
        self.next_direction = next_direction
        self.confidence = confidence
        self.should_continue = should_continue
        self.correction_needed = correction_needed
        self.raw_json = raw_json or {}

    @classmethod
    def from_json(cls, data: dict) -> "ReflectionResult":
        return cls(
            goal_alignment=data.get("goal_alignment", "YES"),
            new_information=data.get("new_information", ""),
            next_direction=data.get("next_direction", ""),
            confidence=data.get("confidence", 80),
            should_continue=data.get("should_continue", True),
            correction_needed=data.get("correction_needed"),
            raw_json=data,
        )

    @classmethod
    def skip(cls, reason: str = "no reflection needed") -> "ReflectionResult":
        """跳过的 Reflection——用于非代码生成步骤或空输出。"""
        return cls(
            goal_alignment="YES",
            new_information=reason,
            should_continue=True,
        )

    def is_drifting(self) -> bool:
        """Agent 是否在偏离目标。"""
        return self.goal_alignment in ("NO", "PARTIALLY") or self.confidence < 40


class ReflectionEngine:
    """ReflAct 反思引擎——构建 Prompt + 解析 LLM 响应。

    用法:
        engine = ReflectionEngine(llm=llm_client)
        result = await engine.reflect(
            goal="检查2024年度应收账款坏账准备",
            thought="需要查看应收账款明细账",
            action="read_file(path='ar_ledger.csv')",
            observation="文件包含1200条记录，金额合计500万元",
        )
        if result.is_drifting():
            # 注入纠正逻辑
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    async def reflect(
        self,
        goal: str,
        thought: str = "",
        action: str = "",
        observation: str = "",
        quick: bool = False,
    ) -> ReflectionResult:
        """运行一次 Reflection——调用 LLM 进行结构化自我评估。

        Args:
            goal: 原始任务目标
            thought: 上一个 Thought 内容
            action: 上一步执行的动作
            observation: Observation 结果
            quick: True=使用轻量 Prompt，更少 Token

        Returns:
            ReflectionResult——包含对齐评估和下一步建议
        """
        if self._llm is None:
            return ReflectionResult.skip("no LLM available")

        if quick:
            prompt = REFLECTION_PROMPT_QUICK.format(
                original_goal=goal,
                last_action=action,
                last_observation=observation[:500],
            )
        else:
            prompt = REFLECTION_PROMPT.format(
                original_goal=goal,
                last_thought=thought,
                last_action=action,
                last_observation=observation[:1000],
            )

        try:
            # 非流式调用——Reflection 不需要逐 token 输出
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt="你是一个 Agent 自我反思系统。评估 Agent 的每一步是否对准原始目标。只输出 JSON。",
                messages=None,
                tools=None,
                task_type="structured_output",  # Inkeep 三层路由
            )
            result = await self._llm.generate(req, task_id="reflection")

            # 解析 JSON——LLM 可能包裹在 Markdown 代码块中
            json_str = result.strip()
            if "```" in json_str:
                # 提取代码块内容
                import re
                match = re.search(r"```(?:json)?\s*([\s\S]*?)```", json_str)
                if match:
                    json_str = match.group(1).strip()

            data = json.loads(json_str)
            return ReflectionResult.from_json(data)

        except json.JSONDecodeError as e:
            logger.debug("reflection_json_parse_failed", error=str(e), raw=result[:200])
            return ReflectionResult.skip(f"JSON parse error: {e}")
        except Exception as e:
            logger.debug("reflection_failed", error=str(e))
            return ReflectionResult.skip(f"Reflection error: {e}")
