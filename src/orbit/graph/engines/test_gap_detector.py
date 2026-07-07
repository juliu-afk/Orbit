"""测试覆盖空洞检测——业务层减熵 P2.

基于函数参数类型 × 已有测试输入值 找未覆盖的边界条件.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("orbit.test_gap")


@dataclass
class TestGap:
    """单个测试覆盖空洞."""
    __test__ = False  # 非 pytest 测试类

    function_name: str
    param_name: str
    param_type: str
    covered_values: list[Any] = field(default_factory=list)
    missing_cases: list[str] = field(default_factory=list)
    # M4: 风险排序字段
    risk_score: float = 0.0  # 综合风险分 (0.0-1.0)
    centrality: float = 0.0   # 代码中心度——多少其他函数依赖此函数
    complexity: float = 0.0   # 改动复杂度
    static_issues: int = 0    # 静态分析发现的问题数


# P1-1: 边界条件用 (标签, 检查函数) 替代纯字符串——
# 检查函数接收已有测试值的 set，返回该边界是否已覆盖
BoundaryChecker = Callable[[set[Any]], bool]


def _checker_any(condition: Callable[[Any], bool]) -> BoundaryChecker:
    """创建检查器——covered 中存在满足条件的值即视为覆盖."""
    return lambda covered: any(condition(v) for v in covered)


# 每种参数类型的边界条件——(标签, 检查器)
BOUNDARY_CASES: dict[str, list[tuple[str, BoundaryChecker]]] = {
    "int": [
        ("值为0", _checker_any(lambda v: v == 0)),
        ("负数", _checker_any(lambda v: isinstance(v, int) and v < 0)),
        ("大整数值", _checker_any(lambda v: isinstance(v, int) and abs(v) > 1000)),
    ],
    "float": [
        ("值为0.0", _checker_any(lambda v: v == 0.0 or v == 0)),
        ("负数", _checker_any(lambda v: isinstance(v, (int, float)) and v < 0)),
        ("正数", _checker_any(lambda v: isinstance(v, (int, float)) and v > 0)),
    ],
    "str": [
        ("空字符串", _checker_any(lambda v: v == "")),
        ("超长字符串", _checker_any(lambda v: isinstance(v, str) and len(v) > 100)),
        ("特殊字符", _checker_any(lambda v: isinstance(v, str) and any(ord(c) > 127 for c in v))),
    ],
    "bool": [
        ("True", _checker_any(lambda v: v is True)),
        ("False", _checker_any(lambda v: v is False)),
    ],
    "list": [
        ("空列表", _checker_any(lambda v: isinstance(v, list) and len(v) == 0)),
        ("单元素", _checker_any(lambda v: isinstance(v, list) and len(v) == 1)),
        ("None", _checker_any(lambda v: v is None)),
    ],
    "dict": [
        ("空字典", _checker_any(lambda v: isinstance(v, dict) and len(v) == 0)),
        (
            "嵌套字典",
            _checker_any(
                lambda v: isinstance(v, dict) and any(isinstance(sv, dict) for sv in v.values())
            ),
        ),
    ],
    "Decimal": [
        (
            "值为0",
            _checker_any(lambda v: str(v) == "0" or getattr(v, "__float__", lambda: 1)() == 0.0),
        ),
        (
            "负数",
            _checker_any(lambda v: isinstance(v, (int, float)) and v < 0 or str(v).startswith("-")),
        ),
    ],
}


class TestGapDetector:
    """静态分析——基于参数类型找出未测试的边界条件.

    用法:
        detector = TestGapDetector()
        gaps = await detector.detect(code_graph, function_name="calculate_tax")
    """
    __test__ = False  # 非 pytest 测试类

    async def detect(self, code_graph: Any, function_name: str) -> list[TestGap]:
        """对指定函数做覆盖空洞检测."""
        gaps: list[TestGap] = []

        func_info = await code_graph.get_function_info(function_name)
        if not func_info:
            logger.debug("test_gap_func_not_found", function=function_name)
            return gaps

        existing_tests = await code_graph.find_tests_for(function_name)

        for param_name, param_type in func_info.get("parameters", {}).items():
            covered = self._extract_covered_values(existing_tests, param_name)
            boundaries = BOUNDARY_CASES.get(param_type, [])
            missing = [label for label, checker in boundaries if not checker(covered)]

            if missing:
                gaps.append(
                    TestGap(
                        function_name=function_name,
                        param_name=param_name,
                        param_type=param_type,
                        covered_values=sorted(str(v) for v in covered),
                        missing_cases=missing,
                    )
                )

        return gaps

    @staticmethod
    def _extract_covered_values(tests: list[dict], param_name: str) -> set[Any]:
        """从测试数据中提取已知覆盖值——返回原始值而非 repr."""
        values: set = set()
        for test in tests:
            params = test.get("params", {})
            if param_name in params:
                values.add(params[param_name])
        return values

    # ── M4: 风险排序 ─────────────────────────────────────────

    async def rank_by_risk(
        self,
        gaps: list[TestGap],
        code_graph: Any = None,
        change_complexity: dict[str, float] | None = None,
        static_issues: dict[str, int] | None = None,
    ) -> list[TestGap]:
        """M4: 对测试缺口按风险排序——对标 TestGapRadar (IEEE TSE 2025)。

        排序因子（14 指标模型中选取 3 个最有效的）:
        1. 代码中心度 — 被多少其他函数调用（code_graph.get_callers）
        2. 改动复杂度 — 函数 cyclomatic complexity 或变更行数
        3. 静态分析发现数 — 同一文件中已有 issues 数

        权重默认值来自 TestGapRadar 论文——积累 30+ 审查后自动调参。

        Returns:
            按 risk_score 降序排列的 TestGap 列表
        """
        change_complexity = change_complexity or {}
        static_issues = static_issues or {}

        for gap in gaps:
            # 因子 1: 代码中心度 (0.0-1.0)
            if code_graph:
                try:
                    callers = await code_graph.get_callers(gap.function_name)
                    caller_count = len(callers) if callers else 0
                    # 归一化: log2(callers+1) / 10 —— 10 个调用方 → 0.35
                    import math
                    gap.centrality = min(1.0, math.log2(caller_count + 1) / 10.0)
                except Exception:
                    gap.centrality = 0.0
            else:
                gap.centrality = 0.2  # 默认中等偏下（无图谱数据时保守假设）

            # 因子 2: 改动复杂度 (0.0-1.0)
            gap.complexity = change_complexity.get(gap.function_name, 0.5)  # 默认中等

            # 因子 3: 静态分析问题数 (归一化 0.0-1.0)
            gap.static_issues = static_issues.get(gap.function_name, 0)
            static_factor = min(1.0, gap.static_issues / 10.0)  # 10+ 个问题 → 1.0

            # 综合风险分: 加权求和
            # 权重: centrality 40% / complexity 35% / static_issues 25%
            gap.risk_score = (
                0.40 * gap.centrality
                + 0.35 * gap.complexity
                + 0.25 * static_factor
            )

        # 按风险分降序排列
        ranked = sorted(gaps, key=lambda g: g.risk_score, reverse=True)

        logger.info(
            "test_gaps_ranked",
            total=len(ranked),
            high_risk=sum(1 for g in ranked if g.risk_score >= 0.7),
            medium_risk=sum(1 for g in ranked if 0.3 <= g.risk_score < 0.7),
            low_risk=sum(1 for g in ranked if g.risk_score < 0.3),
        )
        return ranked
