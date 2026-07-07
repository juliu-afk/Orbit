"""渐进式审查引擎——跨阶段三列对照（PRD→ADR→代码）。

WHY 独立模块: 现有审查系统四个阶段各有一套"预期提取"，但互不通信。
PRD 提取验收标准 → ADR 提取架构约束 → 代码阶段填实际实现。
本模块做跨阶段对比——预期 vs 实际，不是事后全量审查。

对标: 研究报告 §7 渐进式审查 + Testora (ICSE 2026) 行为对比 + RUNE 模式扩展。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger("orbit.review.progressive")


class CheckpointVerdict(str, Enum):
    """检查点判定——预期 vs 实际。"""
    MATCH = "match"           # 完全匹配
    DEVIATION = "deviation"   # 偏离——有实现但不符预期
    PARTIAL = "partial"       # 部分实现
    NOT_FOUND = "not_found"   # 预期有但代码里找不到
    EXCESS = "excess"         # 代码有但预期没有（可能是合理的扩展）


@dataclass
class ReviewCheckpoint:
    """跨阶段审查检查点——从 PRD 到代码的三列对照。

    左列（PRD）: expectation — 代码必须实现什么
    中列（ADR）: adr_constraint — 架构约束/技术决策
    右列（代码）: actual — 实际文件:行号 + 判定
    """

    __test__ = False  # 非 pytest 测试类

    id: str = ""
    source_phase: str = ""        # "prd" | "adr" | "spec"
    source_ref: str = ""          # 出自哪个文档的哪条（可追溯）

    # ── 三列——渐进填充 ──
    expectation: str = ""         # 左列：PRD 阶段——代码必须实现什么
    adr_constraint: str = ""      # 中列：ADR 阶段——架构约束/技术决策
    actual_location: str = ""     # 右列：代码阶段——实际文件:行号
    actual_snippet: str = ""      # 右列：实际代码片段（≤200 字符）

    # ── 判定（代码阶段自动填）──
    verdict: CheckpointVerdict = CheckpointVerdict.NOT_FOUND
    evidence: str = ""            # 证据——测试结果/审查发现/覆盖率数据

    # ── 元数据 ──
    severity: str = "major"       # "critical" | "major" | "minor"
    task_id: str = ""             # 关联的 Task ID


@dataclass
class ProgressiveReviewReport:
    """渐进式审查报告——三列对照的完整结果。"""

    checkpoints: list[ReviewCheckpoint] = field(default_factory=list)
    spec_title: str = ""
    phase: str = ""  # "prd" | "adr" | "code" — 当前填到哪列

    @property
    def matched(self) -> int:
        return sum(1 for c in self.checkpoints if c.verdict == CheckpointVerdict.MATCH)

    @property
    def deviations(self) -> int:
        return sum(1 for c in self.checkpoints if c.verdict == CheckpointVerdict.DEVIATION)

    @property
    def not_found(self) -> int:
        return sum(1 for c in self.checkpoints if c.verdict == CheckpointVerdict.NOT_FOUND)

    @property
    def match_rate(self) -> float:
        total = len(self.checkpoints)
        if total == 0:
            return 1.0
        return self.matched / total

    @property
    def high_severity_gaps(self) -> list[ReviewCheckpoint]:
        """需要人类关注的高严重度缺口。"""
        return [
            c for c in self.checkpoints
            if c.verdict in (CheckpointVerdict.DEVIATION, CheckpointVerdict.NOT_FOUND)
            and c.severity in ("critical", "major")
        ]


class ProgressiveReviewEngine:
    """渐进式审查引擎——从 Spec + PRD/ADR 文本构建检查点，代码阶段填充判定。

    Usage:
        engine = ProgressiveReviewEngine()
        report = engine.build_from_spec(spec, prd_text="", adr_text="")
        # ... 代码生成后 ...
        report = engine.fill_code_column(report, task_results)
    """

    # ── 阶段 1: 从 Spec 构建左列（PRD 预期） ──

    def build_from_spec(
        self,
        spec: Any,  # compose.models.Spec
        prd_text: str = "",
        adr_text: str = "",
    ) -> ProgressiveReviewReport:
        """从 Spec 展开 ReviewCheckpoint 列表——阶段 1+2 调用。

        每个 Task 的 signature/behavior/tests 展开为检查点左列。
        PRD 文本中的验收标准 → 追加检查点左列。
        ADR 文本中的技术决策 → 填充已有检查点的中列。
        """
        checkpoints: list[ReviewCheckpoint] = []

        # 从 Spec.tasks 展开——RUNE 启发增强字段直接成为检查点
        tasks = getattr(spec, "tasks", [])
        for task in tasks:
            task_id = getattr(task, "id", "")
            description = getattr(task, "description", "")

            # signature → 接口实现检查
            sig = getattr(task, "signature", "")
            if sig:
                checkpoints.append(ReviewCheckpoint(
                    id=f"sig_{task_id}",
                    source_phase="spec",
                    source_ref=f"Task {task_id} — signature",
                    expectation=f"函数签名: {sig}",
                    task_id=task_id,
                    severity="critical",
                ))

            # behavior → 行为检查
            behaviors = getattr(task, "behavior", [])
            for i, b in enumerate(behaviors):
                checkpoints.append(ReviewCheckpoint(
                    id=f"beh_{task_id}_{i}",
                    source_phase="spec",
                    source_ref=f"Task {task_id} — behavior[{i}]",
                    expectation=b,
                    task_id=task_id,
                    severity="major",
                ))

            # tests → 测试断言检查
            test_assertions = getattr(task, "tests", [])
            for i, t in enumerate(test_assertions):
                checkpoints.append(ReviewCheckpoint(
                    id=f"test_{task_id}_{i}",
                    source_phase="spec",
                    source_ref=f"Task {task_id} — test[{i}]",
                    expectation=f"测试断言: {t}",
                    task_id=task_id,
                    severity="major",
                ))

            # 至少一个基础检查点——防止空 spec.task
            if not sig and not behaviors and not test_assertions:
                checkpoints.append(ReviewCheckpoint(
                    id=f"desc_{task_id}",
                    source_phase="spec",
                    source_ref=f"Task {task_id} — description",
                    expectation=description[:200] if description else "(无详细描述)",
                    task_id=task_id,
                    severity="major",
                ))

        # 从 PRD 文本提取验收标准 → 追加左列
        if prd_text:
            ac_checkpoints = self._extract_from_prd(prd_text)
            checkpoints.extend(ac_checkpoints)

        # 从 ADR 文本提取架构约束 → 填充已有检查点的中列
        if adr_text:
            self._fill_adr_constraints(checkpoints, adr_text)

        report = ProgressiveReviewReport(
            checkpoints=checkpoints,
            spec_title=getattr(spec, "title", ""),
            phase="prd",
        )
        logger.info(
            "progressive_review_built",
            checkpoints=len(checkpoints),
            has_prd=bool(prd_text),
            has_adr=bool(adr_text),
        )
        return report

    # ── 阶段 3: 填充右列（代码实际） ──

    def fill_code_column(
        self,
        report: ProgressiveReviewReport,
        task_results: dict[str, dict],
        source_files: dict[str, str] | None = None,
    ) -> ProgressiveReviewReport:
        """代码阶段——对每个检查点查找实际实现并判定。

        Args:
            report: 从 build_from_spec 得到的报告（左列+中列已填）
            task_results: {task_id: {output, status, ...}}
            source_files: {file_path: content} 可选——用于精确定位代码位置
        """
        source_files = source_files or {}

        for checkpoint in report.checkpoints:
            task_id = checkpoint.task_id
            if not task_id or task_id not in task_results:
                checkpoint.verdict = CheckpointVerdict.NOT_FOUND
                checkpoint.evidence = "任务未在 results 中找到"
                continue

            result = task_results[task_id]
            output = str(result.get("output", ""))
            status = result.get("status", "unknown")

            if status == "error":
                checkpoint.verdict = CheckpointVerdict.NOT_FOUND
                checkpoint.evidence = f"任务失败: {result.get('error', '')[:200]}"
                continue

            if not output:
                checkpoint.verdict = CheckpointVerdict.NOT_FOUND
                checkpoint.evidence = "任务无输出"
                continue

            # 在输出中搜索预期匹配
            matched, location, snippet = self._search_in_output(
                checkpoint.expectation, output, source_files,
            )
            if matched:
                checkpoint.verdict = CheckpointVerdict.MATCH
                checkpoint.actual_location = location
                checkpoint.actual_snippet = snippet[:200]
                checkpoint.evidence = f"在 {location} 中找到匹配"
            else:
                checkpoint.verdict = CheckpointVerdict.PARTIAL
                checkpoint.evidence = "输出中未找到明确匹配——可能部分实现或命名差异"

            # 检测超出预期的内容（excess）
            if checkpoint.verdict == CheckpointVerdict.MATCH and not checkpoint.expectation:
                checkpoint.verdict = CheckpointVerdict.EXCESS
                checkpoint.evidence = "代码实现了预期之外的功能"

        report.phase = "code"
        logger.info(
            "progressive_review_filled",
            match_rate=f"{report.match_rate:.1%}",
            deviations=report.deviations,
            not_found=report.not_found,
        )
        return report

    # ── 内部 ─────────────────────────────────────────────────

    def _extract_from_prd(self, prd_text: str) -> list[ReviewCheckpoint]:
        """从 PRD 文本提取验收标准 → 左列检查点。

        识别模式: "- " 或 "* " 或 "1. " 开头的列表行（验收标准段）。
        """
        checkpoints: list[ReviewCheckpoint] = []
        lines = prd_text.split("\n")
        in_ac = False
        index = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # 检测验收标准段
            if any(kw in stripped for kw in ["验收标准", "Acceptance Criteria", "AC:"]):
                in_ac = True
                continue
            if in_ac and stripped.startswith("#"):
                in_ac = False
                continue
            if in_ac and (stripped.startswith(("-", "*")) or (stripped and stripped[0].isdigit())):
                import re
                ac_text = re.sub(r'^[\s]*[-*\d.]+\s*', '', stripped)
                checkpoints.append(ReviewCheckpoint(
                    id=f"prd_ac_{index}",
                    source_phase="prd",
                    source_ref="PRD 验收标准",
                    expectation=ac_text,
                    severity="major",
                ))
                index += 1

        return checkpoints

    def _fill_adr_constraints(
        self, checkpoints: list[ReviewCheckpoint], adr_text: str,
    ) -> None:
        """从 ADR 文本提取架构约束 → 填充已有检查点的中列。

        技术决策关键词: "使用" / "采用" / "选择" / "决定" / "Use" / "Decision"。
        匹配到相关检查点 → 填充 adr_constraint。
        """
        import re
        # 提取所有技术决策行
        decision_pattern = re.compile(
            r'(?:使用|采用|选择|决定|Use|Decision)[：:\s]+(.+?)(?:[。.]|$)',
            re.IGNORECASE,
        )
        decisions = decision_pattern.findall(adr_text)
        if not decisions:
            return

        for checkpoint in checkpoints:
            for decision in decisions:
                # 简单关键词匹配——AD 决策是否与检查点相关
                if any(word in checkpoint.expectation.lower() for word in decision.lower().split()):
                    checkpoint.adr_constraint = decision.strip()[:200]
                    break

    def _search_in_output(
        self,
        expectation: str,
        output: str,
        source_files: dict[str, str],
    ) -> tuple[bool, str, str]:
        """在输出中搜索预期匹配。

        Returns:
            (matched, location, snippet)
        """
        # 策略 1: 在 source_files 中搜索函数/类名
        keywords = self._extract_keywords(expectation)
        for file_path, content in source_files.items():
            for kw in keywords:
                if kw in content:
                    # 找到关键字所在行
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if kw in line:
                            return True, f"{file_path}:{i}", line.strip()[:200]

        # 策略 2: 在 output 字符串中搜索
        for kw in keywords:
            if kw in output:
                idx = output.find(kw)
                snippet_start = max(0, idx - 50)
                snippet_end = min(len(output), idx + 150)
                return True, "output", output[snippet_start:snippet_end]

        return False, "", ""

    @staticmethod
    def _extract_keywords(expectation: str) -> list[str]:
        """从预期文本提取搜索关键词。"""
        import re
        # 提取函数名/类名/变量名模式的词
        words = re.findall(r'\b([a-zA-Z_]\w{2,})\b', expectation)
        # 也提取中文关键词（2-4 字）
        cn_words = re.findall(r'[一-鿿]{2,4}', expectation)
        return words + cn_words
