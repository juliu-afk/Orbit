"""需求澄清 Agent——V1-V3 校验函数（纯 Python，零 LLM 成本）。

依次过 V1→V2→V3，任一层失败立即返回。
"""

from __future__ import annotations

import re
from typing import Any

from orbit.agents.clarifier.constants import (
    _CONTRADICTION_PAIRS,
    _OBSERVABLE_VERBS,
    _PLACEHOLDER_WORDS,
)
from orbit.agents.clarifier.models import StructuredPRD, ValidationResult


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
    clean = "".join(c for c in text if c.isalnum() or "一" <= c <= "鿿")
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
