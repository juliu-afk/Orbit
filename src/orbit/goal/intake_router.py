"""Intake Router——智能判定输入形态。

Goal 统一入口——输入可以是模糊需求/PRD文档/技术方案/复数文档。
Intake Router 判定哪些阶段可跳过。fail-open: 判定失败则走完整流程。

判定维度:
1. 结构化程度: 模糊字符串 / 含 frontmatter 的 markdown / 技术方案 markdown
2. 清晰度评分: 0-1, >=0.7 跳过澄清
3. 拆解度评分: 0-1, >=0.7 跳过拆解
"""

from __future__ import annotations

import structlog
from typing import Any

from orbit.goal.models import GoalSession, IntakeDecision

logger = structlog.get_logger("orbit.goal")

# 清晰度检查关键词——启发式评分
CLARITY_MARKERS = {
    "验收标准": 0.18,
    "acceptance criteria": 0.18,
    "验证命令": 0.12,
    "verification": 0.12,
    "约束": 0.10,
    "constraint": 0.10,
    "Non-Goals": 0.10,
    "non-goals": 0.10,
    "pytest": 0.12,
    "npm run": 0.10,
    "tsc": 0.08,
    "exit code": 0.05,
    "测试通过": 0.05,
}

# 拆解度检查关键词
DECOMPOSITION_MARKERS = {
    "## 子任务": 0.20,
    "## Tasks": 0.20,
    "任务列表": 0.15,
    "task list": 0.15,
    "depends_on": 0.20,
    "依赖": 0.15,
    "agent_role": 0.10,
    "拓扑": 0.05,
    "DAG": 0.05,
}


class IntakeRouter:
    """输入形态判定器。

    检测输入形态后决定哪些阶段可跳过。
    fail-open: 不确定 → 走完整流程（不跳过）。

    Usage:
        router = IntakeRouter()
        decision = await router.route(goal)
        if decision.needs_clarify:
            clarified = await clarifier.clarify(goal)
    """

    def __init__(self) -> None:
        pass

    async def route(self, goal: GoalSession) -> IntakeDecision:
        """判定输入形态——返回哪些阶段可跳过。

        Args:
            goal: 用户输入的 Goal（可能是描述/文件路径/复数文档）

        Returns:
            IntakeDecision: 含 needs_clarify/needs_decompose/is_batch
        """
        # 1. 检测输入形态
        form = self._detect_form(goal)

        # 2. 评分
        clarity_score = self._score_clarity(goal.description)
        decomp_score = self._score_decomposition(goal.description)

        # 3. 判定
        result = IntakeDecision(
            needs_clarify=True,
            needs_decompose=True,
            clarity_score=clarity_score,
            decomposition_score=decomp_score,
            is_batch=form == "batch",
        )

        if form == "batch":
            # 复数文档——每个独立判定，但此方法只判整体
            result.is_batch = True
            result.needs_clarify = False  # 批量模式下逐个文档各自判定
            result.needs_decompose = False
            result.confidence = 0.7
            return result

        if clarity_score >= 0.7:
            result.needs_clarify = False
            result.reason_clarify = f"输入清晰度 {clarity_score:.0%}——跳过澄清"
            result.confidence = min(0.9, clarity_score)
        elif clarity_score >= 0.4:
            result.needs_clarify = True
            result.reason_clarify = f"输入部分不足 ({clarity_score:.0%})——补齐缺口"
            result.confidence = clarity_score
        else:
            result.needs_clarify = True
            result.reason_clarify = f"输入模糊 ({clarity_score:.0%})——需要全量澄清"
            result.confidence = 0.4

        if decomp_score >= 0.7:
            result.needs_decompose = False
            result.reason_decompose = f"已有 TaskDAG ({decomp_score:.0%})——跳过拆解"
        elif decomp_score > 0:
            result.reason_decompose = "部分子任务——需补充拆解"

        logger.info(
            "intake_router_decision",
            form=form,
            clarity=round(clarity_score, 2),
            decomp=round(decomp_score, 2),
            needs_clarify=result.needs_clarify,
            needs_decompose=result.needs_decompose,
        )
        return result

    # ── 内部 ──────────────────────────────────────────

    @staticmethod
    def _detect_form(goal: GoalSession) -> str:
        """检测输入形态。

        Returns:
            "vague_string" | "single_file" | "batch" | "task_only"
        """
        desc = goal.description

        # 复数文档——描述中含 "--from" 或 goal.three_tier_memory 中有 batch_goals
        if "--from" in desc or goal.three_tier_memory.get("batch_goals"):
            return "batch"

        # P1-3: 文件路径——路径分隔符 + os.path.exists 双重检测避免误判
        if desc.endswith(".md") and not desc.startswith("--"):
            import os
            if os.path.exists(desc) or "/" in desc or "\\" in desc:
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
                return "single_file"

        # 技术方案——含 TaskDAG 关键词
        if any(kw in desc.lower() for kw in ("## 任务", "## task", "depends_on", "子任务列表")):
            return "task_only"

        return "vague_string"

    @staticmethod
    def _score_clarity(text: str) -> float:
        """评分输入清晰度——启发式关键词匹配。

        0 = 完全模糊（如 "帮我改改代码"）
        1 = 完全清晰（有验收标准+验证命令+约束+Non-Goals）

        WHY 启发式而非 LLM: 预估算阶段不能用昂贵模型。
        """
        score = 0.0

        # 基础分——文本长度暗示结构化程度
        if len(text) > 500:
            score += 0.20
        elif len(text) > 200:
            score += 0.10
        elif len(text) > 50:
            score += 0.05

        # 关键词分
        text_lower = text.lower()
        for marker, weight in CLARITY_MARKERS.items():
            if marker.lower() in text_lower:
                score += weight

        # YAML frontmatter 存在 → 高结构化
        if text.strip().startswith("---"):
            score += 0.15

        return min(1.0, score)

    @staticmethod
    def _score_decomposition(text: str) -> float:
        """评分拆解度——是否已有显式子任务列表。

        0 = 完全未拆解
        1 = 已有完整 TaskDAG（含依赖+角色分配）
        """
        score = 0.0

        text_lower = text.lower()
        for marker, weight in DECOMPOSITION_MARKERS.items():
            if marker.lower() in text_lower:
                score += weight

        # Markdown 表格存在 → 可能是任务表
        if "|" in text and "---" in text:
            # 检测表头是否含 "任务" 或 "task"
            if any(kw in text_lower for kw in ("任务", "task", "描述", "description")):
                score += 0.15

        return min(1.0, score)
