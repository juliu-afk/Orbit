"""需求澄清引擎 (Step 0.3 Phase0 补充).

原始 PRD → 完整性检查 + 矛盾检测 + 可行性评分 → 澄清版 PRD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClarificationIssue:
    """检测到的需求问题。"""

    type: str  # missing_field | contradiction | low_feasibility
    severity: str  # blocking | warning
    field: str = ""  # 问题所在字段
    description: str = ""
    suggestion: str = ""


@dataclass
class ClarificationResult:
    """澄清结果——结构化输出。"""

    original_prd: str
    score: int  # 可行性评分 0-100
    passed: bool  # 是否通过拦截 (≥40)
    issues: list[ClarificationIssue] = field(default_factory=list)
    completeness: dict[str, bool] = field(default_factory=dict)
    # {"has_goal": True, "has_scope": False, "has_acceptance": True, ...}

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "issues": [
                {
                    "type": i.type,
                    "severity": i.severity,
                    "field": i.field,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "completeness": self.completeness,
        }


class ClarificationEngine:
    """需求澄清引擎——启发式规则检测 + 可行性评分。

    用法:
        ce = ClarificationEngine()
        result = ce.clarify("原始 PRD 文本...")
        if result.passed:
            ...  # 进入架构阶段
        else:
            ...  # 展示 issues, 要求用户澄清
    """

    # 互斥修饰词对 (矛盾检测)
    CONTRADICTION_PAIRS: list[tuple[str, str, str]] = [
        (r"必须.*离线", r"必须.*实时", "离线 vs 实时同步矛盾"),
        (r"支持.*并发", r"延迟.*<\s*1\s*ms", "高并发 + 超低延迟物理矛盾"),
        (r"实时同步", r"离线优先", "实时 vs 离线优先级矛盾"),
        (r"零停机", r"全量更新", "零停机 + 全量更新矛盾"),
        (r"无限制", r"预算.*上限", "无限制 vs 预算上限矛盾"),
        (r"强制.*A", r"禁止.*A", "强制+禁止同一条件矛盾"),
    ]

    # 完整性检查项
    COMPLETENESS_CHECKS: list[tuple[str, str, str]] = [
        ("目标", r"(目标|目的|要做什么|需求|需要)", "缺少目标描述"),
        ("范围", r"(范围|Do|Don't|包含|不包含)", "缺少范围边界"),
        ("验收标准", r"(验收|成功标准|AC\d|通过条件)", "缺少验收标准"),
        ("非功能需求", r"(性能|安全|可用|可靠性|并发|延迟|QPS)", "缺少非功能需求"),
        ("边界条件", r"(边界|空数据|异常|错误处理|降级)", "缺少边界条件"),
    ]

    def clarify(self, prd_text: str) -> ClarificationResult:
        """对原始 PRD 执行完整澄清流程。"""
        issues: list[ClarificationIssue] = []
        completeness: dict[str, bool] = {}

        # 1. 完整性检查
        for name, pattern, desc in self.COMPLETENESS_CHECKS:
            found = bool(re.search(pattern, prd_text, re.IGNORECASE))
            completeness[f"has_{name}"] = found
            if not found:
                issues.append(
                    ClarificationIssue(
                        type="missing_field",
                        severity="warning",
                        field=name,
                        description=desc,
                        suggestion=f"请补充{name}相关内容",
                    )
                )

        # 2. 矛盾检测
        for pattern_a, pattern_b, desc in self.CONTRADICTION_PAIRS:
            if re.search(pattern_a, prd_text, re.IGNORECASE) and re.search(
                pattern_b, prd_text, re.IGNORECASE
            ):
                issues.append(
                    ClarificationIssue(
                        type="contradiction",
                        severity="blocking",
                        description=desc,
                        suggestion="请明确优先级或移除其中一个约束",
                    )
                )

        # 3. 可行性评分
        score = self._score(prd_text, completeness, issues)

        return ClarificationResult(
            original_prd=prd_text,
            score=score,
            passed=score >= 40,
            issues=issues,
            completeness=completeness,
        )

    def _score(
        self,
        prd_text: str,
        completeness: dict[str, bool],
        issues: list[ClarificationIssue],
    ) -> int:
        """可行性评分 0-100。

        算法: 完整性 × 40 + 矛盾惩罚 + 文本质量 × 30 + 覆盖度 × 30
        """
        # 完整性分 (40)
        complete_count = sum(1 for v in completeness.values() if v)
        complete_score = (complete_count / max(len(completeness), 1)) * 40

        # 矛盾惩罚: 每个 blocking 矛盾 -20
        contradiction_penalty = sum(20 for i in issues if i.type == "contradiction")

        # 文本质量分 (30): 长度 + 结构化程度
        text_score = min(len(prd_text) / 200, 1.0) * 15  # 至少 200 字
        if re.search(r"(#|背景|需求|方案|验收)", prd_text):
            text_score += 15  # 有结构化标记
        text_score = min(text_score, 30)

        # 覆盖度分 (30): missing_field 每个 -6
        missing_penalty = sum(6 for i in issues if i.type == "missing_field")

        score = int(complete_score - contradiction_penalty + text_score - missing_penalty)
        return max(0, min(100, score))
