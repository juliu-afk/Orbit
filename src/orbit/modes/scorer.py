"""TaskQualityScorer——三维度任务质量评分引擎.

维度1: 用户反馈（从 chat history 关键词提取）
维度2: 会话质量（从 clarifier V1-V3 校验结果）
维度3: 交付结果（从 task_runner 终态）

全部纯函数，零 LLM 调用，零 IO。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


# ── 关键词表 ──────────────────────────────────

# WHY 中文优先: Orbit 用户以中文为主。英文关键词作为兜底。
_POSITIVE_KEYWORDS: tuple[str, ...] = (
    "对", "好的", "确认", "可以", "OK", "ok", "yes", "行", "没问题",
    "就这样", "继续", "下一步", "同意",
)
_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "不对", "不是", "重来", "换个", "错了", "不行", "不要", "取消",
    "重新", "改一下", "换一个", "no", "wrong",
)
_ABANDON_KEYWORDS: tuple[str, ...] = (
    "算了", "不做了", "放弃", "取消任务",
)


@dataclass
class DimensionScore:
    """单维度评分结果."""

    score: float  # 0-1
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskQualityScore:
    """三维度综合评分."""

    task_id: str
    user_satisfaction: float
    session_quality: float
    delivery_outcome: float
    total: float  # 加权总分: 0.3*用户 + 0.3*会话 + 0.4*交付
    detail: dict[str, Any] = field(default_factory=dict)
    scored_at: str = ""

    def __post_init__(self) -> None:
        if not self.scored_at:
            self.scored_at = datetime.now(UTC).isoformat()


class TaskQualityScorer:
    """三维度任务质量评分器——纯函数，无副作用."""

    # ── 维度 1: 用户反馈 ──────────────────────

    @staticmethod
    def score_user_satisfaction(chat_history: list[dict] | None) -> DimensionScore:
        """从 chat history 提取用户正/负面信号.

        Args:
            chat_history: [{role: "user"|"assistant", content: "..."}, ...]

        评分逻辑:
            +0.3 / 正面消息
            -0.5 / 负面消息
            -1.0 / 放弃信号
            clamp to [0, 1]
        """
        if not chat_history:
            return DimensionScore(score=0.5, detail={"reason": "无聊天记录，默认中性"})

        positive_count = 0
        negative_count = 0
        abandoned = False

        for msg in chat_history:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            lower = content.lower()

            if any(kw in lower for kw in _ABANDON_KEYWORDS):
                abandoned = True
                break
            if any(kw in lower for kw in _POSITIVE_KEYWORDS):
                positive_count += 1
            if any(kw in lower for kw in _NEGATIVE_KEYWORDS):
                negative_count += 1

        if abandoned:
            return DimensionScore(score=0.0, detail={"reason": "用户放弃", "abandoned": True})

        # 基础分 0.5 + 调整
        score = 0.5 + positive_count * 0.3 - negative_count * 0.5
        score = max(0.0, min(1.0, score))
        return DimensionScore(
            score=score,
            detail={
                "positive_msgs": positive_count,
                "negative_msgs": negative_count,
                "total_user_msgs": len([m for m in chat_history if m.get("role") == "user"]),
            },
        )

    # ── 维度 2: 会话质量 ──────────────────────

    @staticmethod
    def score_session_quality(clarifier_result: dict | None) -> DimensionScore:
        """从 clarifier PRD 校验结果提取会话质量.

        Args:
            clarifier_result: clarifier execute() 返回的 result dict,
                              含 structured_prd / clarification_status / missing_fields

        评分逻辑:
            V1+V2+V3 全部 passed → +0.4
            clarification_status="ready" → +0.3
            PRD 完整度 → +0.3
        """
        if clarifier_result is None:
            return DimensionScore(score=0.5, detail={"reason": "非 PARSING 任务，跳过"})

        score = 0.0
        detail_parts: dict[str, Any] = {}

        # 检查是否存在 structured_prd
        prd = clarifier_result.get("structured_prd")
        if prd is None:
            return DimensionScore(score=0.2, detail={"reason": "PRD 未产出"})

        # V1-V3 校验（如果 validate_prd 已跑过，结果在 result 中）
        validation_passed = clarifier_result.get("validation_passed", None)
        if validation_passed is True:
            score += 0.4
            detail_parts["validation"] = "V1-V3 passed"
        elif validation_passed is False:
            detail_parts["validation"] = clarifier_result.get("validation_errors", "V1-V3 failed")

        # clarification_status
        status = clarifier_result.get("clarification_status", "")
        if status == "ready":
            score += 0.3
            detail_parts["status"] = "ready"
        else:
            detail_parts["status"] = status or "unknown"

        # PRD 完整度: goal 长度 + scope 长度 + acceptance 数量
        goal = (prd.get("goal") or "").strip()
        scope = (prd.get("scope") or "").strip()
        ac = prd.get("acceptance_criteria") or []

        goal_score = min(len(goal) / 50, 1.0) if goal else 0.0
        scope_score = min(len(scope) / 50, 1.0) if scope else 0.0
        ac_score = min(len(ac) / 3, 1.0)
        completeness = (goal_score + scope_score + ac_score) / 3
        score += completeness * 0.3

        detail_parts["goal_len"] = len(goal)
        detail_parts["scope_len"] = len(scope)
        detail_parts["ac_count"] = len(ac)

        return DimensionScore(score=min(score, 1.0), detail=detail_parts)

    # ── 维度 3: 交付结果 ──────────────────────

    @staticmethod
    def score_delivery(
        task_state: str,
        review_passed: bool = False,
        has_regression: bool = False,
    ) -> DimensionScore:
        """从任务终态提取交付质量.

        Args:
            task_state: DONE / FAILED / CANCELLED
            review_passed: VERIFYING 阶段审查是否通过
            has_regression: 是否引入了回归 bug
        """
        score = 0.0

        # 任务完成
        if task_state == "DONE":
            score += 0.4
        elif task_state == "FAILED":
            score += 0.0

        # 审查通过
        if review_passed:
            score += 0.3

        # 无回归
        if not has_regression:
            score += 0.2

        # G6 TODO: 需求变更检测——对比同 session 内是否重新 clarify。
        # 当前版本占位，G6 自扩展模式生成器落地后补充真实判断逻辑。

        return DimensionScore(
            score=min(score, 1.0),
            detail={
                "task_state": task_state,
                "review_passed": review_passed,
                "has_regression": has_regression,
            },
        )

    # ── 综合评分 ──────────────────────────────

    @classmethod
    def score(
        cls,
        task_id: str,
        chat_history: list[dict] | None = None,
        clarifier_result: dict | None = None,
        task_state: str = "UNKNOWN",
        review_passed: bool = False,
        has_regression: bool = False,
    ) -> TaskQualityScore:
        """计算三维度综合评分.

        WHY 交付权重最高 (0.4): 最终交付质量 > 过程体验 > 用户态度。
        """
        dim1 = cls.score_user_satisfaction(chat_history)
        dim2 = cls.score_session_quality(clarifier_result)
        dim3 = cls.score_delivery(task_state, review_passed, has_regression)

        total = 0.3 * dim1.score + 0.3 * dim2.score + 0.4 * dim3.score

        return TaskQualityScore(
            task_id=task_id,
            user_satisfaction=round(dim1.score, 3),
            session_quality=round(dim2.score, 3),
            delivery_outcome=round(dim3.score, 3),
            total=round(total, 3),
            detail={
                "dim1": dim1.detail,
                "dim2": dim2.detail,
                "dim3": dim3.detail,
            },
        )
