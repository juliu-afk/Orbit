"""测试覆盖空洞检测——业务层减熵 P2.

基于函数参数类型 × 已有测试输入值 找未覆盖的边界条件.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("orbit.test_gap")


@dataclass
class TestGap:
    """单个测试覆盖空洞."""

    function_name: str
    param_name: str
    param_type: str
    covered_values: list[Any] = field(default_factory=list)
    missing_cases: list[str] = field(default_factory=list)


# P2: 每种参数类型的边界条件清单
BOUNDARY_CASES: dict[str, list[str]] = {
    "int": ["0", "负数", "最大整数"],
    "float": ["0.0", "负数", "正数"],
    "str": ["空字符串", "超长字符串", "特殊字符"],
    "bool": ["True", "False"],
    "list": ["空列表", "单元素", "None"],
    "dict": ["空字典", "嵌套字典"],
    "Decimal": ["0", "负数", "非常大的值"],
}


class TestGapDetector:
    """静态分析——基于参数类型找出未测试的边界条件.

    用法:
        detector = TestGapDetector()
        gaps = await detector.detect(code_graph, function_name="calculate_tax")
    """

    async def detect(self, code_graph: Any, function_name: str) -> list[TestGap]:
        """对指定函数做覆盖空洞检测.

        Args:
            code_graph: CodeGraphEngine 实例
            function_name: 要检测的函数名

        Returns:
            覆盖空洞列表
        """
        gaps: list[TestGap] = []

        # 从代码图谱获取函数签名
        func_info = await code_graph.get_function_info(function_name)
        if not func_info:
            logger.debug("test_gap_func_not_found", function=function_name)
            return gaps

        # 从代码图谱获取已有测试
        existing_tests = await code_graph.find_tests_for(function_name)

        # 对每个参数检查边界条件
        for param_name, param_type in func_info.get("parameters", {}).items():
            covered = self._extract_covered_values(existing_tests, param_name)
            boundaries = BOUNDARY_CASES.get(param_type, [])
            missing = [b for b in boundaries if not self._is_covered(b, covered)]

            if missing:
                gaps.append(
                    TestGap(
                        function_name=function_name,
                        param_name=param_name,
                        param_type=param_type,
                        covered_values=list(covered),
                        missing_cases=missing,
                    )
                )

        return gaps

    @staticmethod
    def _extract_covered_values(tests: list[dict], param_name: str) -> set:
        """从测试数据中提取已知覆盖值."""
        values: set = set()
        for test in tests:
            params = test.get("params", {})
            if param_name in params:
                values.add(repr(params[param_name]))
        return values

    @staticmethod
    def _is_covered(boundary: str, covered: set) -> bool:
        """简单检查边界是否已有覆盖."""
        return boundary.lower() in {str(c).lower() for c in covered}
