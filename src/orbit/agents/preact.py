"""PreAct 预测规划 (Phase D1).

对标: PreAct (2025)——在 ReAct Action 之前增加预测阶段，让 Agent 先预测行动可能结果再决定是否执行。

WHY:
  Orbit 当前 ReAct: Thought → Action → Observation → (错了→回滚)
  PreAct:  Thought → [Predict] → Action → Observation
  预测阶段用轻量 LLM 调用评估"这个 Action 会成功吗？会推进目标吗？"
  如果预测失败概率高 → 跳过 Action，生成替代方案。减少回滚次数。

设计:
  - 规则预测器: 快速检查（工具是否存在/参数格式是否正确）
  - LLM 预测器: 语义判断（这个 Action 是否对目标有效）
  - 预测置信度 < 阈值 → 生成替代 Action
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient
    from orbit.tools.registry import ToolRegistry

import structlog

logger = structlog.get_logger("orbit.agents.preact")

# 轻量预测 Prompt——不需要完整上下文，只看当前 Action
PREDICT_PROMPT = """You are about to execute an action. Predict if it will succeed.

Goal: {goal}
Planned Action: {action_name}
Arguments: {action_args}
Context (last observation): {observation}

Answer these in JSON:
1. will_succeed (true/false): Will this tool call execute without errors?
2. advances_goal (true/false): Will the result advance the original goal?
3. confidence (0-100): How confident are you in this prediction?
4. risk (low/medium/high): What's the risk level?
5. alternative: If you think this will fail, suggest a better action (or null)

JSON only, no markdown:"""


@dataclass
class PreActPrediction:
    will_succeed: bool = True
    advances_goal: bool = True
    confidence: int = 80
    risk: str = "low"
    alternative: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "PreActPrediction":
        return cls(
            will_succeed=data.get("will_succeed", True),
            advances_goal=data.get("advances_goal", True),
            confidence=data.get("confidence", 80),
            risk=data.get("risk", "low"),
            alternative=data.get("alternative"),
        )

    def should_skip(self, threshold: int = 50) -> bool:
        """是否应该跳过此 Action。"""
        return (not self.will_succeed and self.confidence > threshold) or \
               (self.risk == "high" and self.confidence > 70)

    def should_rethink(self, threshold: int = 60) -> bool:
        """是否需要重新考虑——不推进目标且置信度高。"""
        return not self.advances_goal and self.confidence > threshold


class PreActEngine:
    """PreAct 预测引擎——Action 前预测+替代方案生成。

    用法:
        engine = PreActEngine(llm=llm, tools=tools)
        pred = await engine.predict(goal="审计AR", action="exec_command", args={"cmd":"rm -rf /"}, obs="...")
        if pred.should_skip():
            # 不执行，用 alternative 或让 Agent 重新想
    """

    def __init__(self, llm: LLMClient | None = None, tools: ToolRegistry | None = None) -> None:
        self._llm = llm
        self._tools = tools

    async def predict(
        self, goal: str, action_name: str, action_args: dict | None = None,
        observation: str = "", use_llm: bool = True,
    ) -> PreActPrediction:
        """预测 Action 的可能结果。

        规则预测器（快速）→ LLM 预测器（语义判断，可选）。
        """
        args = action_args or {}

        # 第 1 层: 规则预测器——零 Token 成本
        rule_pred = self._rule_predict(action_name, args)
        if rule_pred and rule_pred.confidence > 80:
            return rule_pred

        # 第 2 层: LLM 预测器——语义判断
        if use_llm and self._llm:
            return await self._llm_predict(goal, action_name, args, observation)

        return rule_pred or PreActPrediction()

    def _rule_predict(self, action_name: str, args: dict) -> PreActPrediction | None:
        """规则预测器——检查工具可用性和参数合法性。"""
        if self._tools is None:
            return None

        # 工具是否存在
        tools = self._tools.list_all()
        tool_names = {t.get("function", {}).get("name", "") for t in tools}
        if action_name not in tool_names:
            return PreActPrediction(
                will_succeed=False, advances_goal=False, confidence=95,
                risk="high",
                alternative=f"工具 '{action_name}' 不存在。可用工具: {sorted(tool_names)[:10]}",
            )

        # 危险命令检测
        dangerous = {"rm -rf", "sudo", "chmod 777", "DROP TABLE", "DELETE FROM", "format"}
        for k, v in args.items():
            val = str(v).lower()
            for d in dangerous:
                if d.lower() in val:
                    return PreActPrediction(
                        will_succeed=False, advances_goal=False, confidence=90,
                        risk="high",
                        alternative=f"检测到危险命令: '{d}'。请使用安全的替代方案。",
                    )

        return None  # 规则无法判断，交给 LLM

    async def _llm_predict(
        self, goal: str, action_name: str, args: dict, observation: str,
    ) -> PreActPrediction:
        """LLM 预测器——语义判断 Action 的有效性。"""
        prompt = PREDICT_PROMPT.format(
            goal=goal, action_name=action_name,
            action_args=json.dumps(args, ensure_ascii=False)[:500],
            observation=observation[:500],
        )
        try:
            from orbit.gateway.schemas import LLMRequest
            req = LLMRequest(
                prompt=prompt, system_prompt="You are an action predictor. Output JSON only.",
                task_type="structured_output",
            )
            result = await self._llm.generate(req, task_id="preact")
            data = json.loads(result.content.strip())
            return PreActPrediction.from_json(data)
        except Exception:
            logger.debug("preact_llm_failed", exc_info=True)
            return PreActPrediction()  # fail-open: 不阻塞
