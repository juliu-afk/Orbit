
"""需求澄清 Agent（自然语言交互 PR）。

职责：通过多轮对话把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。
经 LLMClient 网关调用 LLM，chat 端点不直接接触 LLM。

WHY 独立角色：现有 5 个 Agent（architect/developer/reviewer/qa/config_manager）
都不负责需求澄清，澄清是编程任务的前置环节，需要专属 Agent。

校验链（V1-V3 纯 Python，V4 熵监控在 LLMClient 流式分支，V5 结构契约在本文件）：
  V5: StructuredPRD.model_validate_json — 输出 JSON schema 校验
  V1: validate_prd 字段完整性 — 非空/非占位/长度
  V2: validate_prd 一致性 — 语义呼应/可观测动词/无字面矛盾
  V3: validate_prd 矛盾检测 — goal↔acceptance / scope↔constraints 方向冲突
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.gateway.schemas import LLMRequest
from orbit.scheduler.clarifier import ClarificationEngine

logger = structlog.get_logger()


# ---- V5 结构契约：Agent 输出的结构化 PRD schema ----


class StructuredPRD(BaseModel):
    """结构化 PRD——ClarifierAgent 输出的需求文档。

    V5 校验直接 model_validate_json，不符合 schema 即拦截。
    """

    goal: str = ""
    scope: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    # 仅当需要用户选验收标准时填，否则空数组（PRD 验收候选策略）
    acceptance_options: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """V1-V3 校验结果。

    passed=False 时 failed_layer 和 reasons 告诉 Agent 本轮要问什么。
    """

    passed: bool
    failed_layer: str = ""  # V1 | V2 | V3 | ""
    reasons: list[str] = Field(default_factory=list)


# ---- System Prompt（PRD 定义全文，领域适配 + 澄清维度 + 输出格式） ----

CLARIFIER_SYSTEM_PROMPT = """你是 Orbit 系统的需求澄清 Agent（ClarifierAgent），角色定位：资深需求工程师 + 技术架构师。

职责：通过多轮对话，把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。

【用户画像与领域适配（关键规则）】
你服务的用户可能不是程序员（如律师做法律软件、会计做财务软件）。必须：
1. 首轮从 project.tags / project.description 识别用户领域（法律/财务/医疗/...），判断用户是否为非技术背景。
2. 永远用用户能听懂的领域语言提问，不抛技术黑话。
3. 技术决策不甩给用户——Agent 基于项目栈自行推荐方案+利弊，让用户选"目标"而非选"技术"。
4. 领域术语桥接：用户说"留置权""坏账计提"等领域术语时，你翻译成软件需求并在 reply 中复述确认。

【澄清维度】
必问（三项齐备才能 ready）：
  1. goal — 要解决的核心问题，一句话
  2. scope — 做哪些/不做哪些，改哪里
  3. acceptance_criteria — 怎么验证做完了
按需（对话出现相关线索才追问）：
  · 数据/状态/并发 → 边界条件
  · 性能/安全/兼容 → 非功能约束
  · 指定技术 → 技术选型确认
  · bug类需求 → 复现条件
  · 涉及现有功能 → 影响面

【工作原则】
1. 每轮只问 1-2 个最关键的问题，避免轰炸用户。
2. 按优先级推进：goal > scope > acceptance_criteria > 按需维度。
3. 基于已确认信息推进，绝不重复已答过的问题。
4. 当用户说不清 acceptance_criteria 时：基于 goal 主动生成 2-3 个候选验收条件让用户选，
   并提供"其它"选项允许用户自由输入，而非追问"你的验收标准是什么"。
5. 当 goal + scope + acceptance_criteria 三者齐备 → 输出 structured_prd 并标记 ready。

【输出格式】严格 JSON，不要输出 JSON 以外的内容：
{
  "reply": "你这一轮对用户说的话（追问/给候选/确认）",
  "clarification_status": "clarifying" | "ready",
  "structured_prd": {
    "goal": "已明确的目标",
    "scope": "已明确的范围",
    "acceptance_criteria": ["条件1", "条件2"],
    "edge_cases": [],
    "constraints": [],
    "acceptance_options": []
  },
  "missing_fields": ["goal","scope"]
}
"""


# ---- 可观测动词白名单（V2 用） ----
# WHY 固定白名单：验收标准必须可验证，"用户体验好"这种主观描述无法验收。
_OBSERVABLE_VERBS: tuple[str, ...] = (
    "返回",
    "更新",
    "触发",
    "显示",
    "拒绝",
    "锁定",
    "创建",
    "删除",
    "保存",
    "发送",
    "重试",
    "取消",
    "关闭",
    "记录",
    "通知",
    "生成",
    "校验",
    "跳过",
    "等待",
    "清理",
    "迁移",
    "回滚",
)

# 占位词黑名单（V1 用）
_PLACEHOLDER_WORDS: tuple[str, ...] = (
    "待定",
    "tbd",
    "todo",
    "...",
    "？？？",
    "暂无",
    "未知",
)

# 矛盾方向对——统一从 ClarificationEngine 取（P0 消重）
# WHY: 不再各自维护一份 CONTRADICTION_PAIRS，单点维护在 scheduler/clarifier.py
_CONTRADICTION_PAIRS: list[tuple[str, str, str]] = ClarificationEngine.CONTRADICTION_PAIRS


class ClarifierAgent(BaseAgent):
    """需求澄清 Agent。

    经 LLMClient 网关调 LLM，多轮收敛用户需求为结构化 PRD。
    无状态——对话历史由 chat 端点从 SessionRegistry 构建后注入 context。
    """

    role = AgentRole.CLARIFIER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行一轮需求澄清。

        输入 context 含：project（项目信息）、history（最近 10 轮对话）、confirmed（已确认点）。
        返回 result：reply / clarification_status / structured_prd / missing_fields。
        """
        user_message = input_data.task
        context = input_data.context

        # mock 模式：无 LLM 时返回模板，供 CI 测试（参照现有 DeveloperAgent mock 模式）
        if self.llm is None:
            return AgentOutput(result=self._mock_response(user_message, context))

        prompt = self._build_prompt(user_message, context)
        task_id = str(context.get("task_id", ""))

        # 调 LLM 网关——chat 端点不直接接触 LLM，只通过 Agent
        try:
            resp = await self.llm.generate(
                LLMRequest(prompt=prompt, system_prompt=self.system_prompt()),
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
            hist_text = "\n".join(
                f"  {m.get('role','user')}: {m.get('content','')}"
                for m in history[-20:]  # 最近 10 轮 = 20 条消息
            )
            parts.append(f"【对话历史】\n{hist_text}")
        if confirmed:
            parts.append(f"【已确认需求点】\n{json.dumps(confirmed, ensure_ascii=False)}")

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
        return CLARIFIER_SYSTEM_PROMPT


# ---- V1-V3 校验函数 ----


def validate_prd(prd: StructuredPRD | dict[str, Any]) -> ValidationResult:
    """V1-V3 分层校验（纯 Python，零 LLM 成本）。

    依次过 V1→V2→V3，任一层失败立即返回。
    """
    # 统一转 StructuredPRD
    if isinstance(prd, dict):
        try:
            prd = StructuredPRD.model_validate(prd)
        except Exception:
            return ValidationResult(
                passed=False,
                failed_layer="V1",
                reasons=["structured_prd 结构不符合 schema"],
            )

    # ---- V1 字段完整性 ----
    v1_reasons: list[str] = []
    if not prd.goal or len(prd.goal.strip()) < 8:
        v1_reasons.append("goal 为空或过短（需 >=8 字符）")
    elif _is_placeholder(prd.goal):
        v1_reasons.append("goal 是占位词，请描述具体目标")
    if not prd.scope or len(prd.scope.strip()) < 8:
        v1_reasons.append("scope 为空或过短（需 >=8 字符）")
    elif _is_placeholder(prd.scope):
        v1_reasons.append("scope 是占位词，请描述具体范围")
    elif not _has_boundary(prd.scope):
        v1_reasons.append("scope 缺少边界描述（需说明做哪些/不做哪些）")
    if not prd.acceptance_criteria:
        v1_reasons.append("acceptance_criteria 为空")
    else:
        for i, ac in enumerate(prd.acceptance_criteria):
            if not ac or len(ac.strip()) < 5:
                v1_reasons.append(f"acceptance_criteria[{i}] 为空或过短（需 >=5 字符）")

    if v1_reasons:
        return ValidationResult(passed=False, failed_layer="V1", reasons=v1_reasons)

    # ---- V2 一致性 ----
    v2_reasons: list[str] = []
    # goal 核心名词在 scope/acceptance 有呼应
    if not _goal_has_resonance(prd.goal, prd.scope, prd.acceptance_criteria):
        v2_reasons.append("goal 的核心词在 scope/acceptance 中无呼应")
    # 每条 acceptance 含可观测动词
    for i, ac in enumerate(prd.acceptance_criteria):
        if not _has_observable_verb(ac):
            v2_reasons.append(f"acceptance_criteria[{i}] 不可观测（需含返回/更新/触发等动词）")
    # scope 内部无字面矛盾
    scope_contradiction = _check_internal_contradiction(prd.scope)
    if scope_contradiction:
        v2_reasons.append(scope_contradiction)

    if v2_reasons:
        return ValidationResult(passed=False, failed_layer="V2", reasons=v2_reasons)

    # ---- V3 矛盾检测 ----
    v3_reasons: list[str] = _check_cross_contradiction(
        prd.goal, prd.acceptance_criteria, prd.scope, prd.constraints
    )
    if v3_reasons:
        return ValidationResult(passed=False, failed_layer="V3", reasons=v3_reasons)

    return ValidationResult(passed=True)


# ---- 校验辅助函数 ----


def _is_placeholder(text: str) -> bool:
    """检查是否为占位词。"""
    lower = text.strip().lower()
    return any(p in lower for p in _PLACEHOLDER_WORDS)


def _has_boundary(scope: str) -> bool:
    """检查 scope 是否含边界描述（做/不做/包含/排除/仅/只 等）。"""
    markers = ("做", "不做", "包含", "排除", "仅", "只", "范围", "涉及", "限于", "边界")
    return any(m in scope for m in markers)


def _extract_keywords(text: str, min_len: int = 2) -> list[str]:
    """提取中文核心词（简单分词：2-4 字滑窗）。"""
    clean = "".join(c for c in text if c.isalnum() or "\u4e00" <= c <= "\u9fff")
    if len(clean) < min_len:
        return [clean] if clean else []
    return [clean[i : i + 2] for i in range(len(clean) - 1)]


def _goal_has_resonance(goal: str, scope: str, acceptance: list[str]) -> bool:
    """goal 核心词在 scope 或 acceptance 中至少出现一次。"""
    keywords = _extract_keywords(goal)
    combined = (scope + " " + " ".join(acceptance)).lower()
    return any(kw.lower() in combined for kw in keywords)


def _has_observable_verb(text: str) -> bool:
    """检查是否含可观测动词。"""
    return any(v in text for v in _OBSERVABLE_VERBS)


def _check_internal_contradiction(text: str) -> str:
    """检查文本内部字面矛盾（如"支持并发"+"不做并发控制"）。"""
    pairs = [
        ("支持并发", "不做并发控制", "scope 内部并发描述矛盾"),
        ("实时", "离线", "scope 内部实时/离线矛盾"),
    ]
    lower = text.lower()
    for a, b, desc in pairs:
        if a in lower and b in lower:
            return desc
    return ""


def _check_cross_contradiction(
    goal: str,
    acceptance: list[str],
    scope: str,
    constraints: list[str],
) -> list[str]:
    """V3：goal↔acceptance / scope↔constraints 方向冲突检测。"""
    reasons: list[str] = []
    combined = (goal + " " + scope).lower()
    ac_text = " ".join(acceptance).lower()
    constraint_text = " ".join(constraints).lower()

    for kw_a, kw_b, desc in _CONTRADICTION_PAIRS:
        # goal/scope 出现 A 且 acceptance 出现 B → 用 regex 匹配（P0 消重后统一格式）
        if re.search(kw_a, combined) and re.search(kw_b, ac_text):
            reasons.append(desc)
        # scope 出现 A 且 constraints 出现 B → regex 匹配
        if re.search(kw_a, scope.lower()) and re.search(kw_b, constraint_text):
            reasons.append(desc)

    return reasons

"""需求澄清 Agent（自然语言交互 PR）。

职责：通过多轮对话把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。
经 LLMClient 网关调用 LLM，chat 端点不直接接触 LLM。

WHY 独立角色：现有 5 个 Agent（architect/developer/reviewer/qa/config_manager）
都不负责需求澄清，澄清是编程任务的前置环节，需要专属 Agent。

校验链（V1-V3 纯 Python，V4 熵监控在 LLMClient 流式分支，V5 结构契约在本文件）：
  V5: StructuredPRD.model_validate_json — 输出 JSON schema 校验
  V1: validate_prd 字段完整性 — 非空/非占位/长度
  V2: validate_prd 一致性 — 语义呼应/可观测动词/无字面矛盾
  V3: validate_prd 矛盾检测 — goal↔acceptance / scope↔constraints 方向冲突
"""


import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

from orbit.agents.base import AgentInput, AgentOutput, AgentRole, BaseAgent
from orbit.gateway.schemas import LLMRequest
from orbit.scheduler.clarifier import ClarificationEngine

logger = structlog.get_logger()


# ---- V5 结构契约：Agent 输出的结构化 PRD schema ----


class StructuredPRD(BaseModel):
    """结构化 PRD——ClarifierAgent 输出的需求文档。

    V5 校验直接 model_validate_json，不符合 schema 即拦截。
    """

    goal: str = ""
    scope: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    # 仅当需要用户选验收标准时填，否则空数组（PRD 验收候选策略）
    acceptance_options: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """V1-V3 校验结果。

    passed=False 时 failed_layer 和 reasons 告诉 Agent 本轮要问什么。
    """

    passed: bool
    failed_layer: str = ""  # V1 | V2 | V3 | ""
    reasons: list[str] = Field(default_factory=list)


# ---- System Prompt（PRD 定义全文，领域适配 + 澄清维度 + 输出格式） ----

CLARIFIER_SYSTEM_PROMPT = """你是 Orbit 系统的需求澄清 Agent（ClarifierAgent），角色定位：资深需求工程师 + 技术架构师。

职责：通过多轮对话，把用户模糊的自然语言需求收敛为无歧义、可执行的结构化 PRD。

【用户画像与领域适配（关键规则）】
你服务的用户可能不是程序员（如律师做法律软件、会计做财务软件）。必须：
1. 首轮从 project.tags / project.description 识别用户领域（法律/财务/医疗/...），判断用户是否为非技术背景。
2. 永远用用户能听懂的领域语言提问，不抛技术黑话。
3. 技术决策不甩给用户——Agent 基于项目栈自行推荐方案+利弊，让用户选"目标"而非选"技术"。
4. 领域术语桥接：用户说"留置权""坏账计提"等领域术语时，你翻译成软件需求并在 reply 中复述确认。

【澄清维度】
必问（三项齐备才能 ready）：
  1. goal — 要解决的核心问题，一句话
  2. scope — 做哪些/不做哪些，改哪里
  3. acceptance_criteria — 怎么验证做完了
按需（对话出现相关线索才追问）：
  · 数据/状态/并发 → 边界条件
  · 性能/安全/兼容 → 非功能约束
  · 指定技术 → 技术选型确认
  · bug类需求 → 复现条件
  · 涉及现有功能 → 影响面

【工作原则】
1. 每轮只问 1-2 个最关键的问题，避免轰炸用户。
2. 按优先级推进：goal > scope > acceptance_criteria > 按需维度。
3. 基于已确认信息推进，绝不重复已答过的问题。
4. 当用户说不清 acceptance_criteria 时：基于 goal 主动生成 2-3 个候选验收条件让用户选，
   并提供"其它"选项允许用户自由输入，而非追问"你的验收标准是什么"。
5. 当 goal + scope + acceptance_criteria 三者齐备 → 输出 structured_prd 并标记 ready。

【输出格式】严格 JSON，不要输出 JSON 以外的内容：
{
  "reply": "你这一轮对用户说的话（追问/给候选/确认）",
  "clarification_status": "clarifying" | "ready",
  "structured_prd": {
    "goal": "已明确的目标",
    "scope": "已明确的范围",
    "acceptance_criteria": ["条件1", "条件2"],
    "edge_cases": [],
    "constraints": [],
    "acceptance_options": []
  },
  "missing_fields": ["goal","scope"]
}
"""


# ---- 可观测动词白名单（V2 用） ----
# WHY 固定白名单：验收标准必须可验证，"用户体验好"这种主观描述无法验收。
_OBSERVABLE_VERBS: tuple[str, ...] = (
    "返回",
    "更新",
    "触发",
    "显示",
    "拒绝",
    "锁定",
    "创建",
    "删除",
    "保存",
    "发送",
    "重试",
    "取消",
    "关闭",
    "记录",
    "通知",
    "生成",
    "校验",
    "跳过",
    "等待",
    "清理",
    "迁移",
    "回滚",
)

# 占位词黑名单（V1 用）
_PLACEHOLDER_WORDS: tuple[str, ...] = (
    "待定",
    "tbd",
    "todo",
    "...",
    "？？？",
    "暂无",
    "未知",
)

# 矛盾方向对——统一从 ClarificationEngine 取（P0 消重）
# WHY: 不再各自维护一份 CONTRADICTION_PAIRS，单点维护在 scheduler/clarifier.py
_CONTRADICTION_PAIRS: list[tuple[str, str, str]] = ClarificationEngine.CONTRADICTION_PAIRS


class ClarifierAgent(BaseAgent):
    """需求澄清 Agent。

    经 LLMClient 网关调 LLM，多轮收敛用户需求为结构化 PRD。
    无状态——对话历史由 chat 端点从 SessionRegistry 构建后注入 context。
    """

    role = AgentRole.CLARIFIER

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """执行一轮需求澄清。

        输入 context 含：project（项目信息）、history（最近 10 轮对话）、confirmed（已确认点）。
        返回 result：reply / clarification_status / structured_prd / missing_fields。
        """
        user_message = input_data.task
        context = input_data.context

        # mock 模式：无 LLM 时返回模板，供 CI 测试（参照现有 DeveloperAgent mock 模式）
        if self.llm is None:
            return AgentOutput(result=self._mock_response(user_message, context))

        prompt = self._build_prompt(user_message, context)
        task_id = str(context.get("task_id", ""))

        # 调 LLM 网关——chat 端点不直接接触 LLM，只通过 Agent
        try:
            resp = await self.llm.generate(
                LLMRequest(prompt=prompt, system_prompt=self.system_prompt()),
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
            hist_text = "\n".join(
                f"  {m.get('role','user')}: {m.get('content','')}"
                for m in history[-20:]  # 最近 10 轮 = 20 条消息
            )
            parts.append(f"【对话历史】\n{hist_text}")
        if confirmed:
            parts.append(f"【已确认需求点】\n{json.dumps(confirmed, ensure_ascii=False)}")

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
        return CLARIFIER_SYSTEM_PROMPT


# ---- V1-V3 校验函数 ----


def validate_prd(prd: StructuredPRD | dict[str, Any]) -> ValidationResult:
    """V1-V3 分层校验（纯 Python，零 LLM 成本）。

    依次过 V1→V2→V3，任一层失败立即返回。
    """
    # 统一转 StructuredPRD
    if isinstance(prd, dict):
        try:
            prd = StructuredPRD.model_validate(prd)
        except Exception:
            return ValidationResult(
                passed=False,
                failed_layer="V1",
                reasons=["structured_prd 结构不符合 schema"],
            )

    # ---- V1 字段完整性 ----
    v1_reasons: list[str] = []
    if not prd.goal or len(prd.goal.strip()) < 8:
        v1_reasons.append("goal 为空或过短（需 >=8 字符）")
    elif _is_placeholder(prd.goal):
        v1_reasons.append("goal 是占位词，请描述具体目标")
    if not prd.scope or len(prd.scope.strip()) < 8:
        v1_reasons.append("scope 为空或过短（需 >=8 字符）")
    elif _is_placeholder(prd.scope):
        v1_reasons.append("scope 是占位词，请描述具体范围")
    elif not _has_boundary(prd.scope):
        v1_reasons.append("scope 缺少边界描述（需说明做哪些/不做哪些）")
    if not prd.acceptance_criteria:
        v1_reasons.append("acceptance_criteria 为空")
    else:
        for i, ac in enumerate(prd.acceptance_criteria):
            if not ac or len(ac.strip()) < 5:
                v1_reasons.append(f"acceptance_criteria[{i}] 为空或过短（需 >=5 字符）")

    if v1_reasons:
        return ValidationResult(passed=False, failed_layer="V1", reasons=v1_reasons)

    # ---- V2 一致性 ----
    v2_reasons: list[str] = []
    # goal 核心名词在 scope/acceptance 有呼应
    if not _goal_has_resonance(prd.goal, prd.scope, prd.acceptance_criteria):
        v2_reasons.append("goal 的核心词在 scope/acceptance 中无呼应")
    # 每条 acceptance 含可观测动词
    for i, ac in enumerate(prd.acceptance_criteria):
        if not _has_observable_verb(ac):
            v2_reasons.append(f"acceptance_criteria[{i}] 不可观测（需含返回/更新/触发等动词）")
    # scope 内部无字面矛盾
    scope_contradiction = _check_internal_contradiction(prd.scope)
    if scope_contradiction:
        v2_reasons.append(scope_contradiction)

    if v2_reasons:
        return ValidationResult(passed=False, failed_layer="V2", reasons=v2_reasons)

    # ---- V3 矛盾检测 ----
    v3_reasons: list[str] = _check_cross_contradiction(
        prd.goal, prd.acceptance_criteria, prd.scope, prd.constraints
    )
    if v3_reasons:
        return ValidationResult(passed=False, failed_layer="V3", reasons=v3_reasons)

    return ValidationResult(passed=True)


# ---- 校验辅助函数 ----


def _is_placeholder(text: str) -> bool:
    """检查是否为占位词。"""
    lower = text.strip().lower()
    return any(p in lower for p in _PLACEHOLDER_WORDS)


def _has_boundary(scope: str) -> bool:
    """检查 scope 是否含边界描述（做/不做/包含/排除/仅/只 等）。"""
    markers = ("做", "不做", "包含", "排除", "仅", "只", "范围", "涉及", "限于", "边界")
    return any(m in scope for m in markers)


def _extract_keywords(text: str, min_len: int = 2) -> list[str]:
    """提取中文核心词（简单分词：2-4 字滑窗）。"""
    clean = "".join(c for c in text if c.isalnum() or "\u4e00" <= c <= "\u9fff")
    if len(clean) < min_len:
        return [clean] if clean else []
    return [clean[i : i + 2] for i in range(len(clean) - 1)]


def _goal_has_resonance(goal: str, scope: str, acceptance: list[str]) -> bool:
    """goal 核心词在 scope 或 acceptance 中至少出现一次。"""
    keywords = _extract_keywords(goal)
    combined = (scope + " " + " ".join(acceptance)).lower()
    return any(kw.lower() in combined for kw in keywords)


def _has_observable_verb(text: str) -> bool:
    """检查是否含可观测动词。"""
    return any(v in text for v in _OBSERVABLE_VERBS)


def _check_internal_contradiction(text: str) -> str:
    """检查文本内部字面矛盾（如"支持并发"+"不做并发控制"）。"""
    pairs = [
        ("支持并发", "不做并发控制", "scope 内部并发描述矛盾"),
        ("实时", "离线", "scope 内部实时/离线矛盾"),
    ]
    lower = text.lower()
    for a, b, desc in pairs:
        if a in lower and b in lower:
            return desc
    return ""


def _check_cross_contradiction(
    goal: str,
    acceptance: list[str],
    scope: str,
    constraints: list[str],
) -> list[str]:
    """V3：goal↔acceptance / scope↔constraints 方向冲突检测。"""
    reasons: list[str] = []
    combined = (goal + " " + scope).lower()
    ac_text = " ".join(acceptance).lower()
    constraint_text = " ".join(constraints).lower()

    for kw_a, kw_b, desc in _CONTRADICTION_PAIRS:
        # goal/scope 出现 A 且 acceptance 出现 B → 用 regex 匹配（P0 消重后统一格式）
        if re.search(kw_a, combined) and re.search(kw_b, ac_text):
            reasons.append(desc)
        # scope 出现 A 且 constraints 出现 B → regex 匹配
        if re.search(kw_a, scope.lower()) and re.search(kw_b, constraint_text):
            reasons.append(desc)

    return reasons

