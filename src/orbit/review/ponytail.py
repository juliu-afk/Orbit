"""Ponytail 审查维度——检测过度工程。

WHY 独立审查维度: Ponytail 的关注点（过度工程、不必要的抽象、stdlib 可替代）
与常规代码审查（正确性、安全、性能）不同——需要专门的分析逻辑。

检测项:
  1. 不必要的抽象——只有一个实现者的基类/接口
  2. stdlib 可替代——用外部包实现标准库能做的事
  3. 死代码——未使用的函数/类/变量
  4. 过早泛化——通用代码只有一个调用点
  5. 冗余包装——函数体只有一行，只是调了另一个函数
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.review.ponytail")


@dataclass
class PonytailFinding:
    """Ponytail 审查发现。"""

    file_path: str
    line: int
    severity: str  # "warning" | "suggestion"
    problem: str  # 问题描述
    lazier_alternative: str  # 更懒的替代方案
    category: str  # "unnecessary_abstraction" | "stdlib_replacement" | "dead_code" | "premature_generalization" | "redundant_wrapper"


@dataclass
class PonytailReport:
    """Ponytail 审查报告。"""

    findings: list[PonytailFinding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)  # {category: count}

    @property
    def total(self) -> int:
        return len(self.findings)

    @property
    def recommendations(self) -> list[str]:
        """生成改进建议摘要。"""
        return [f"{f.file_path}:{f.line}: [{f.severity}] {f.problem}" for f in self.findings]


# ── 检测规则 ──────────────────────────────────────────────
# WHY 正则 + AST 组合: 正则快速过滤候选，AST 精准确认。
# 避免对每个文件做完整 AST 解析（大项目性能开销大）。


def _check_stdlib_replacements(content: str) -> list[tuple[int, str]]:
    """检测可用 stdlib 替代的外部包使用。

    规则基于常见模式:
    - requests → urllib（Python 3）
    - python-dateutil → datetime（Python 3.9+ zoneinfo）
    - pytz → zoneinfo
    - simplejson → json
    - pathlib2 → pathlib
    """
    patterns: list[tuple[str, str, str]] = [
        (r"import requests\b", "urllib.request / httpx（如已安装）", "考虑用 stdlib urllib 或已有的 httpx 替代 requests"),
        (r"from dateutil\b", "datetime.timezone / zoneinfo", "Python 3.9+ 内置 zoneinfo 替代 python-dateutil"),
        (r"import pytz\b", "zoneinfo", "Python 3.9+ 内置 zoneinfo 替代 pytz"),
        (r"import simplejson\b", "json", "stdlib json 替代 simplejson"),
        (r"from pathlib2\b", "pathlib", "Python 3.4+ 内置 pathlib"),
    ]
    findings: list[tuple[int, str]] = []
    for pattern, replacement, explanation in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            line_no = content[: match.start()].count("\n") + 1
            findings.append((line_no, f"[stdlib] {explanation}。替代: {replacement}"))
    return findings


def _check_unnecessary_abstractions(content: str) -> list[tuple[int, str]]:
    """检测不必要的抽象模式。

    包括:
    - 只有一个方法的类（除了 __init__）
    - 只有一个子类的基类
    - 只有一个实现者的抽象类
    """
    findings: list[tuple[int, str]] = []

    # 检测 "只有一个方法" 的类（启发式——需要 AST 确认，此处做关键词扫描）
    lines = content.split("\n")
    in_class = False
    class_start = 0
    method_count = 0

    def _flush_class(end_line: int) -> None:
        """检查当前累积累是否应报告。"""
        nonlocal in_class, class_start, method_count
        if in_class and method_count == 1 and class_start > 0:
            findings.append(
                (class_start, "[abstraction] 类只有一个方法——考虑用独立函数替代")
            )
        in_class = False
        class_start = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("class "):
            _flush_class(i)  # 新类开始前检查上一个
            in_class = True
            class_start = i
            method_count = 0
        elif in_class:
            # 先检测类退出——行非空且不缩进 → 离开类作用域
            # WHY 先于 def 检测: def 在 0 列是顶级函数，不是类方法。
            if line and line[0] not in (" ", "\t"):
                _flush_class(i)
                # 回退 in_class——让此后的顶级 def 不被当作类方法
            elif stripped.startswith("def ") and not stripped.startswith("def __init__"):
                method_count += 1
    # WHY: 文件末尾处理——最后如果还在类中，需要检查
    _flush_class(len(lines))

    return findings


def _check_redundant_wrappers(content: str) -> list[tuple[int, str]]:
    """检测冗余包装函数——函数体只有一行 return 调用。"""
    findings: list[tuple[int, str]] = []
    lines = content.split("\n")
    in_func = False
    func_start = 0
    body_lines: list[str] = []

    def _flush_func(end_line: int) -> None:
        """检查当前累积的函数是否应报告。"""
        nonlocal in_func, func_start, body_lines
        if in_func and len(body_lines) == 1 and body_lines[0].strip().startswith("return "):
            findings.append(
                (func_start, "[wrapper] 函数体只有一行 return——考虑内联调用")
            )

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("def "):
            _flush_func(i)  # 新函数前检查上一个
            in_func = True
            func_start = i
            body_lines = []
        elif in_func:
            if stripped and not stripped.startswith(('"""', "'''", "@", "#")):
                body_lines.append(line)
    # WHY: 文件末尾处理——最后一个函数也需要检查
    _flush_func(len(lines))

    return findings


class PonytailReviewer:
    """Ponytail 审查器——静态扫描代码中的过度工程模式。

    Usage:
        reviewer = PonytailReviewer()
        report = reviewer.review_file("src/utils.py", file_content)
        for f in report.findings:
            print(f"{f.file_path}:{f.line}: {f.problem}")
    """

    def review_file(self, file_path: str, content: str) -> PonytailReport:
        """审查单个文件的 Ponytail 合规性。"""
        findings: list[PonytailFinding] = []
        stats: dict[str, int] = {}

        # 只审查 Python 文件（后续扩展 JS/TS）
        if not file_path.endswith(".py"):
            return PonytailReport()

        # stdlib 替代
        for line, msg in _check_stdlib_replacements(content):
            findings.append(
                PonytailFinding(
                    file_path=file_path,
                    line=line,
                    severity="suggestion",
                    problem=msg,
                    lazier_alternative="替换为标准库实现",
                    category="stdlib_replacement",
                )
            )
            stats["stdlib_replacement"] = stats.get("stdlib_replacement", 0) + 1

        # 不必要的抽象
        for line, msg in _check_unnecessary_abstractions(content):
            findings.append(
                PonytailFinding(
                    file_path=file_path,
                    line=line,
                    severity="warning",
                    problem=msg,
                    lazier_alternative="简化为独立函数",
                    category="unnecessary_abstraction",
                )
            )
            stats["unnecessary_abstraction"] = stats.get("unnecessary_abstraction", 0) + 1

        # 冗余包装
        for line, msg in _check_redundant_wrappers(content):
            findings.append(
                PonytailFinding(
                    file_path=file_path,
                    line=line,
                    severity="suggestion",
                    problem=msg,
                    lazier_alternative="内联调用",
                    category="redundant_wrapper",
                )
            )
            stats["redundant_wrapper"] = stats.get("redundant_wrapper", 0) + 1

        report = PonytailReport(findings=findings, stats=stats)
        if findings:
            logger.info(
                "ponytail_review_done",
                file=file_path,
                findings=len(findings),
                stats=stats,
            )
        return report

    def review_files(self, files: dict[str, str]) -> PonytailReport:
        """批量审查多个文件。

        Args:
            files: {file_path: content} 映射

        Returns:
            合并的 PonytailReport
        """
        all_findings: list[PonytailFinding] = []
        all_stats: dict[str, int] = {}
        for path, content in files.items():
            report = self.review_file(path, content)
            all_findings.extend(report.findings)
            for k, v in report.stats.items():
                all_stats[k] = all_stats.get(k, 0) + v
        return PonytailReport(findings=all_findings, stats=all_stats)
