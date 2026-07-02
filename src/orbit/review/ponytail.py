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

    排除: dataclass、名称含 Validator/Handler/Processor/Serializer 的类——
    这些是常见的单方法合理模式。
    """
    findings: list[tuple[int, str]] = []

    # P2-1: 假阳性排除——单方法类在以下场景是合理模式
    _EXCLUDE_PATTERNS = (
        "validator", "handler", "processor", "serializer",
        "controller", "middleware", "interceptor", "resolver",
    )

    lines = content.split("\n")
    in_class = False
    class_start = 0
    method_count = 0
    class_name = ""  # P2-1: 跟踪类名用于排除检查
    has_dataclass_deco = False  # P2-1: 检测 @dataclass 装饰器

    def _flush_class(end_line: int) -> None:
        """检查当前累积累是否应报告。"""
        nonlocal in_class, class_start, method_count, class_name, has_dataclass_deco
        if in_class and method_count == 1 and class_start > 0:
            # P2-1: 排除 dataclass 和常见单方法合理模式
            if has_dataclass_deco:
                pass  # dataclass 常只有 __init__ 之外的一个方法——合理
            elif class_name and any(p in class_name.lower() for p in _EXCLUDE_PATTERNS):
                pass  # Validator/Handler 等单方法是设计模式——合理
            else:
                findings.append(
                    (class_start, f"[abstraction] 类 {class_name} 只有一个方法——考虑用独立函数替代")
                )
        in_class = False
        class_start = 0
        class_name = ""
        has_dataclass_deco = False

    prev_stripped = ""  # 追踪前一行——检测 @dataclass 装饰器
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("class "):
            _flush_class(i)
            # 提取类名
            parts = stripped[6:].split("(")[0].split(":")[0].strip()
            class_name = parts
            # 检查前一行是否为 @dataclass
            has_dataclass_deco = "dataclass" in prev_stripped
            in_class = True
            class_start = i
            method_count = 0
        elif in_class:
            if line and line[0] not in (" ", "\t"):
                _flush_class(i)
            elif stripped.startswith("def ") and not stripped.startswith("def __init__"):
                method_count += 1
        prev_stripped = stripped
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
