"""需求澄清 Agent（自然语言交互 PR）。

职责：通过多轮对话把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。
经 LLMClient 网关调用 LLM，chat 端点不直接接触 LLM。

WHY 独立角色：现有 5 个 Agent（architect/developer/reviewer/qa/config_manager）
都不负责需求澄清，澄清是编程任务的前置环节，需要专属 Agent。

校验链（V1-V3 纯 Python，V4 熵监控在 LLMClient 流式分支，V5 结构契约在 _parse_llm_output）：
  V5: StructuredPRD.model_validate_json — 输出 JSON schema 校验
  V1: validate_prd 字段完整性 — 非空/非占位/长度
  V2: validate_prd 一致性 — 语义呼应/可观测动词/无字面矛盾
  V3: validate_prd 矛盾检测 — goal↔acceptance / scope↔constraints 方向冲突
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, Field

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.agents.clarifier.constants import CLARIFIER_SYSTEM_PROMPT
from orbit.agents.clarifier.models import StructuredPRD
from orbit.gateway.schemas import LLMRequest
from orbit.scheduler.clarifier import ClarificationEngine

logger = structlog.get_logger()


class ClarifierAgent(BaseAgent):
    """需求澄清 Agent。

    经 LLMClient 网关调 LLM，多轮收敛用户需求为结构化 PRD。
    无状态——对话历史由 chat 端点从 SessionRegistry 构建后注入 context。

    G1 Mode File System (grill-me): 行为参数从 self._mode 读取——
    _mode=None 时降级到内置默认行为（深度优先+推荐答案+代码库优先）。
    """

    role = AgentRole.CLARIFIER

    # G1: 从 mode 读取行为参数（降级默认值 = 当前内置行为）
    @property
    def _question_strategy(self) -> str:
        """提问策略——优先 mode 配置，降级 depth_first."""
        if getattr(self, "_mode", None) is not None:
            return self._mode.behavior.question_strategy.value
        return "depth_first"

    @property
    def _require_recommendation(self) -> bool:
        """是否每个问题必须带推荐答案."""
        if getattr(self, "_mode", None) is not None:
            return self._mode.behavior.require_recommendation
        return True

    @property
    def _codebase_first(self) -> bool:
        """是否代码库优先（能查代码就不问用户）."""
        if getattr(self, "_mode", None) is not None:
            return self._mode.behavior.codebase_first
        return True

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行一轮需求澄清。

        输入 context 含：project（项目信息）、history（最近 10 轮对话）、confirmed（已确认点）。
        返回 result：reply / clarification_status / structured_prd / missing_fields。
        """
        user_message = input_data.task
        context = input_data.context

        # G6: 检测 mode 调优意图——用户说"快点"/"问细点"时不走 LLM，直接改 mode
        try:
            from orbit.modes.tuner import ModePreset, ModeTuner
            from orbit.modes.loader import ModeLoader

            intent = ModeTuner.detect_intent(user_message)
            if intent is not None:
                loader = ModeLoader()
                new_config = ModeTuner.apply_preset(loader, "clarify", intent)
                if new_config:
                    self._mode = new_config  # 更新当前实例立即生效
                    strategy_label = {
                        ModePreset.FAST: "快速模式（广度优先，每分支 ≤8 问）",
                        ModePreset.DEEP: "深入模式（深度优先，每分支 ≤30 问）",
                        ModePreset.RESET: "默认模式（深度优先，每分支 ≤20 问）",
                    }.get(intent, str(intent))
                    return AgentOutput(
                        status="ok",
                        result={
                            "reply": f"已切换到 {strategy_label}。",
                            "clarification_status": "clarifying",
                            "structured_prd": None,
                            "missing_fields": [],
                        },
                    )
        except Exception:
            pass  # fail-open: mode 调优失败不影响正常流程

        # mock 模式：无 LLM 时返回模板，供 CI 测试（参照现有 DeveloperAgent mock 模式）
        if self.llm is None:
            return AgentOutput(result=self._mock_response(user_message, context))

        prompt = self._build_prompt(user_message, context)
        task_id = str(context.get("task_id", ""))

        # 调 LLM 网关——chat 端点不直接接触 LLM，只通过 Agent
        try:
            resp = await self.llm.generate(
                LLMRequest(
                    prompt=prompt,
                    system_prompt=self.system_prompt(),
                    # Inkeep 借鉴 #1: 注入 task_type 用于模型路由
                    task_type=context.get("task_type"),
                ),
                task_id,
            )
        except Exception as e:
            # V4 熵监控（HighEntropyError）或其他网关异常 → 降级不阻断会话
            error_type = type(e).__name__
            logger.warning("clarifier_llm_failed", error=str(e), error_type=error_type)
            # WHY 暴露错误类型给用户：帮助区分网络/鉴权/配额问题
            return AgentOutput(
                status="error",
                result={
                    "reply": f"暂时无法分析（{error_type}），请稍后重试。",
                    "clarification_status": "clarifying",
                    "structured_prd": None,
                    "missing_fields": ["goal", "scope", "acceptance_criteria"],
                },
                error=str(e),
            )

        # V5 结构契约：解析 JSON 并校验 schema
        parsed = self._parse_llm_output(resp.content)
        if parsed is None:
            # LLM 输出非合法 JSON → 降级
            logger.warning("clarifier_json_parse_failed", raw=resp.content[:200])
            return AgentOutput(
                status="error",
                result={
                    "reply": "我需要再确认一下你的需求，能否补充更多细节？",
                    "clarification_status": "clarifying",
                    "structured_prd": None,
                    "missing_fields": ["goal", "scope", "acceptance_criteria"],
                },
                error="LLM 输出 JSON 解析失败",
            )

        # G6: 注入模式可见性前缀——用户看到 [🔍 clarify·深度模式]
        try:
            from orbit.modes.indicator import ModeIndicator

            mode_name = getattr(self, "_mode", None)
            if mode_name is not None:
                mode_name = mode_name.name if hasattr(mode_name, "name") else None
            prefix = ModeIndicator.for_agent(
                mode_name=mode_name,
                question_strategy=self._question_strategy,
                max_questions=(
                    self._mode.behavior.max_questions_per_branch
                    if self._mode is not None and hasattr(self._mode, "behavior")
                    else None
                ),
            )
            if "reply" in parsed:
                parsed["reply"] = f"{prefix} {parsed['reply']}"
        except Exception:
            pass  # fail-open: 前缀失败不影响回复

        return AgentOutput(status="ok", result=parsed)

    def _build_prompt(self, user_message: str, context: dict[str, Any]) -> str:
        """构建 user prompt：注入项目信息 + 对话历史 + 已确认点。"""
        project = context.get("project", {})
        history = context.get("history", [])
        confirmed = context.get("confirmed", {})

        parts: list[str] = [f"【用户本轮消息】\n{user_message}"]

        if project:
            parts.append(
                f"【项目信息】\n名称：{project.get('name','')}\n"
                f"描述：{project.get('description','')}\n"
                f"标签：{project.get('tags',[])}"
            )

        if history:
            from orbit.agents.context_util import _build_history_block

            hist_text = _build_history_block(history)
            parts.append(f"【对话历史】\n{hist_text}")

        if confirmed:
            parts.append(f"【已确认需求点】\n{json.dumps(confirmed, ensure_ascii=False)}")

        # G2: 注入上下文阶段——Agent 据此调整分析深度
        stage = context.get("stage", 1)
        if stage >= 2:
            stage_hint = (
                "【上下文深度: Level 2】已加载代码图谱和对话记忆。"
                "可以利用这些信息做更深入的分析，交叉验证用户需求与代码库实际情况。"
            )
            # 如果有图谱查询结果，注入已找到的符号
            l2 = context.get("l2", {})
            found = l2.get("symbols_found", [])
            missing = l2.get("symbols_missing", [])
            if found:
                stage_hint += f"\n代码库中存在的相关符号: {', '.join(found[:10])}"
            if missing:
                stage_hint += f"\n代码库中不存在的符号（可能是新模块）: {', '.join(missing[:10])}"
            parts.append(stage_hint)
        elif stage >= 3:
            parts.append(
                "【上下文深度: Level 3】已加载架构决策记录和历史教训。"
                "可以参考历史决策和已知问题模式。"
            )
        # else stage=1: 基础上下文，不追加提示

        parts.append("【请输出】按 system prompt 规定的 JSON 格式输出本轮澄清结果。")
        return "\n\n".join(parts)

    def _parse_llm_output(self, raw: str) -> dict[str, Any] | None:
        """解析 LLM 输出为 dict，并过 V5 结构契约校验。

        WHY 宽容解析：LLM 可能在 JSON 外包裹 markdown ```json 围栏，需剥离。
        """
        text = raw.strip()
        # 剥离 markdown 代码围栏
        if text.startswith("```"):
            lines = text.split("\n")
            # 去首行 ``` 和末行 ```
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        # V5：校验 structured_prd 子对象符合 schema
        prd_raw = data.get("structured_prd")
        if prd_raw is not None:
            try:
                prd = StructuredPRD.model_validate(prd_raw)
                data["structured_prd"] = prd.model_dump()
            except Exception:
                # 结构不合规 → 视为解析失败，触发上层降级
                return None

        return data

    def _mock_response(self, user_message: str, context: dict[str, Any]) -> dict[str, Any]:
        """mock 模式模板回复（无 LLM 时，供 CI）。"""
        return {
            "reply": f"[mock] 收到你的需求：{user_message}。能否补充你想解决的核心问题？",
            "clarification_status": "clarifying",
            "structured_prd": None,
            "missing_fields": ["goal", "scope", "acceptance_criteria"],
        }

    def system_prompt(self) -> str:
        """构建 system prompt——注入模式行为规则。

        基于 CLARIFIER_SYSTEM_PROMPT，根据 mode 配置追加行为指令。
        """
        base = CLARIFIER_SYSTEM_PROMPT
        mode_config = getattr(self, "_mode", None)
        if mode_config is None:
            return base

        # 基于 mode 行为参数动态追加规则
        mode_rules: list[str] = []
        strategy = self._question_strategy
        if strategy == "breadth_first":
            mode_rules.append(
                "【Mode 行为覆盖】使用 BFS 广度优先策略——每轮列出相关维度供用户选择，"
                "而非聚焦单一分支深挖。每分支 ≤8 问后切下一个维度。"
            )
        elif strategy == "depth_first":
            mode_rules.append(
                "【Mode 行为覆盖】使用 DFS 深度优先策略——聚焦当前最重要的维度深挖，"
                "每个分支完全穷尽后再开下一个。"
            )

        max_q = mode_config.behavior.max_questions_per_branch
        if max_q > 0:
            mode_rules.append(f"每分支最多 {max_q} 问——超限自动切下一维度。")

        if not self._require_recommendation:
            mode_rules.append("不给推荐答案——让用户完全自由回答。")

        if self._codebase_first:
            mode_rules.append("先查代码再问用户。不要问用户能从代码中直接读取的问题。")

        if mode_rules:
            return base + "\n\n" + "\n".join(mode_rules)
        return base
