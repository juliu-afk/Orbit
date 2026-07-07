"""测试报告生成器 —— 人类可读摘要卡片 + Agent 可消费结构化数据 + CrossReport。

WHY 独立文件：报告格式与编排逻辑解耦——后续 UI 调整只改此文件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from orbit.testing.gate import GateDecision, TestRunResult
from orbit.testing.redundancy_check import FrameworkFitReport


@dataclass
class CrossValidation:
    """一条交叉验证——测试和审查在同一代码点上的结论对比。"""
    target: str  # 如 "users.py:45::create_user"
    test_says: str
    review_says: str
    aligned: bool


@dataclass
class DivergentPoint:
    """分歧——测试通过但审查拒绝/警告，人类必须决策。"""
    target: str
    test_verdict: str   # "PASSED"
    review_verdict: str  # "WARNING" | "REJECTED"
    review_reason: str
    suggestion: str


@dataclass
class CrossReport:
    """测试 + 审查的合并报告——人类只看这一份。"""
    task_id: str
    test_result: TestRunResult
    review_result: dict | None = None  # 来自 review/ 模块的审查结果
    cross_validations: list[CrossValidation] = field(default_factory=list)
    consensus: str = "test_only"  # "aligned" | "divergent" | "test_only" | "review_only"
    divergent_points: list[DivergentPoint] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_aligned(self) -> bool:
        return self.consensus == "aligned"

    @property
    def needs_human_decision(self) -> bool:
        return len(self.divergent_points) > 0


class TestReporter:
    """生成各种格式的测试报告。"""

    def build_summary_card(
        self,
        result: TestRunResult,
        decision: GateDecision,
        framework: FrameworkFitReport | None = None,
    ) -> dict:
        """生成聊天流内嵌的摘要卡片 JSON。

        Returns:
            前端 TestResultCard.vue 渲染所需的 JSON 结构。
        """
        card: dict = {
            "type": "test_result",
            "task_id": result.task_id,
            "summary": {
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "coverage_pct": round(result.coverage_pct * 100),
                "mutation_score": (
                    round(result.mutation_score * 100) if result.mutation_score is not None else None
                ),
                "duration_sec": round(result.duration_sec, 1),
                "repair_attempts": result.repair_attempts,
            },
            "verdict": decision.value,
            "verdict_label": self._verdict_label(decision),
            "verdict_color": self._verdict_color(decision),
            "framework_warnings": [],
            "errors": result.errors[:5],  # 最多展示 5 条错误
        }

        # 框架适配警告
        if framework:
            card["framework_warnings"] = [
                {"severity": w.severity.value, "detail": w.detail, "suggestion": w.suggestion}
                for w in framework.warnings
            ]
            if framework.has_blockings:
                card["framework_blockings"] = [
                    {"detail": b.detail, "suggestion": b.suggestion}
                    for b in framework.blockings
                ]

        return card

    def build_detail_panel(
        self,
        result: TestRunResult,
        decision: GateDecision,
        framework: FrameworkFitReport | None = None,
        cases: list[dict] | None = None,
    ) -> dict:
        """生成抽屉面板的详细信息 JSON。

        Returns:
            前端 TestPanel.vue（完整模式）渲染所需的 JSON。
        """
        detail = self.build_summary_card(result, decision, framework)
        detail["cases"] = cases or []
        detail["coverage_gaps"] = []  # Phase 2 填充
        detail["ab_result"] = None    # Phase 3 填充
        return detail

    def build_cross_report(
        self,
        task_id: str,
        test_result: TestRunResult,
        review_result: dict | None = None,
    ) -> CrossReport:
        """合并测试结果和审查结果为 CrossReport。

        WHY 合并：人类不看两份独立报告——只看一张卡片，只处理分歧点。
        """
        cross = CrossReport(
            task_id=task_id,
            test_result=test_result,
            review_result=review_result,
        )

        if not review_result:
            cross.consensus = "test_only"
            return cross

        # 交叉验证——测试和审查在同一代码点上的结论
        review_issues = review_result.get("issues", [])
        review_files = {i.get("file", "") for i in review_issues}

        # 简化：审查提出的每个 issue 与测试结果交叉比对
        for issue in review_issues:
            file = issue.get("file", "")
            line = issue.get("line", 0)
            target = f"{file}:{line}" if line else file
            severity = issue.get("severity", "info")
            message = issue.get("message", "")

            # 检查测试是否已覆盖这个位置
            test_says = "已覆盖" if self._is_covered_by_tests(file, test_result) else "未覆盖"

            aligned = severity != "blocking"  # 审查 blocking + 测试通过 = 分歧

            cross.cross_validations.append(CrossValidation(
                target=target,
                test_says=test_says,
                review_says=message,
                aligned=aligned,
            ))

            if not aligned:
                cross.divergent_points.append(DivergentPoint(
                    target=target,
                    test_verdict="PASSED" if test_result.failed == 0 else "FAILED",
                    review_verdict=severity.upper(),
                    review_reason=message,
                    suggestion=issue.get("suggestion", "请人类决策"),
                ))

        # 共识判定
        if cross.divergent_points:
            cross.consensus = "divergent"
        else:
            cross.consensus = "aligned"

        return cross

    def _verdict_label(self, decision: GateDecision) -> str:
        mapping = {
            GateDecision.PASSED: "通过",
            GateDecision.FAILED: "不通过",
            GateDecision.SUPPLEMENT: "需补充",
            GateDecision.FAILED_PERMANENT: "转人工",
        }
        return mapping.get(decision, decision.value)

    def _verdict_color(self, decision: GateDecision) -> str:
        mapping = {
            GateDecision.PASSED: "green",
            GateDecision.FAILED: "red",
            GateDecision.SUPPLEMENT: "yellow",
            GateDecision.FAILED_PERMANENT: "red",
        }
        return mapping.get(decision, "gray")

    def _is_covered_by_tests(self, file: str, result: TestRunResult) -> bool:
        """简化判断——后续 Phase 2 用覆盖率 JSON 精确匹配。"""
        # 当前：有测试结果且没有失败 → 认为有关联覆盖
        return result.passed > 0 and result.failed == 0
