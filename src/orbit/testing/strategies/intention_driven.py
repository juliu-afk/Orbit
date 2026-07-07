"""意图驱动测试生成 —— Phase 1 MVP 唯一策略。

WHY 意图驱动: 显式告诉 LLM 测试意图（不隐式推测），比纯代码生成覆盖率高 94%（IntUT, ICSE 2025）。
"""

from __future__ import annotations

from dataclasses import dataclass

from orbit.testing.intention import TestIntention


@dataclass
class GeneratedTest:
    """一条生成的测试代码。"""
    name: str  # 测试函数名
    code: str  # 完整测试代码
    target: str  # 被测目标
    type: str  # "positive" | "negative" | "edge" | "invariant"


class IntentionDrivenGenerator:
    """基于 TestIntention 生成测试代码。

    输入: TestIntention（从 intention.py 提取）
    输出: GeneratedTest 列表（可写文件或直接沙箱执行）
    """

    def __init__(self, gateway=None):
        """初始化。

        Args:
            gateway: LiteLLM 网关（Phase 1 可选——可纯模板生成基础测试骨架）。
        """
        self._gateway = gateway

    async def generate(
        self,
        intention: TestIntention,
        source_code: str,
    ) -> list[GeneratedTest]:
        """根据测试意图生成测试代码。

        Phase 1 MVP: 纯模板生成（不调 LLM）——生成 pytest 测试骨架。
        Phase 1 后续: gateway 可用时 → LLM 增强模板。
        """
        tests: list[GeneratedTest] = []

        # 正向路径 → 测试函数
        for i, positive in enumerate(intention.positive):
            tests.append(GeneratedTest(
                name=f"test_{self._safe_name(intention.target)}_positive_{i}",
                code=self._build_positive_test(intention, positive),
                target=intention.target,
                type="positive",
            ))

        # 异常路径 → 测试函数
        for i, negative in enumerate(intention.negative):
            tests.append(GeneratedTest(
                name=f"test_{self._safe_name(intention.target)}_negative_{i}",
                code=self._build_negative_test(intention, negative),
                target=intention.target,
                type="negative",
            ))

        # 边界条件 → 测试函数
        for i, edge in enumerate(intention.edge_cases):
            tests.append(GeneratedTest(
                name=f"test_{self._safe_name(intention.target)}_edge_{i}",
                code=self._build_edge_test(intention, edge),
                target=intention.target,
                type="edge",
            ))

        # 如果不变量存在 → PBT 骨架（Phase 2 由 Hypothesis 填充）
        for i, invariant in enumerate(intention.invariants):
            tests.append(GeneratedTest(
                name=f"test_{self._safe_name(intention.target)}_invariant_{i}",
                code=self._build_invariant_skeleton(intention, invariant),
                target=intention.target,
                type="invariant",
            ))

        return tests

    def _safe_name(self, name: str) -> str:
        """将目标名转为合法的 Python 标识符片段。"""
        return name.replace("::", "_").replace(".", "_").replace("/", "_")

    def _build_positive_test(self, intention: TestIntention, desc: str) -> str:
        """生成一条正向测试的 pytest 骨架。"""
        func_name_parts = intention.target.replace("::", ".").split(".")
        func_short = func_name_parts[-1] if func_name_parts else "function"

        return f'''# 正向: {desc}
def test_{func_short}_positive():
    """{desc}"""
    # TODO: 准备输入参数
    # result = {func_short}(valid_args)
    # assert result is not None
    pass
'''

    def _build_negative_test(self, intention: TestIntention, desc: str) -> str:
        """生成一条异常测试的 pytest 骨架。"""
        func_name_parts = intention.target.replace("::", ".").split(".")
        func_short = func_name_parts[-1] if func_name_parts else "function"

        return f'''# 异常: {desc}
import pytest

def test_{func_short}_negative():
    """{desc}"""
    # TODO: 准备异常输入
    # with pytest.raises(ExpectedError):
    #     {func_short}(invalid_args)
    pass
'''

    def _build_edge_test(self, intention: TestIntention, desc: str) -> str:
        """生成一条边界测试的 pytest 骨架。"""
        func_name_parts = intention.target.replace("::", ".").split(".")
        func_short = func_name_parts[-1] if func_name_parts else "function"

        return f'''# 边界: {desc}
def test_{func_short}_edge():
    """{desc}"""
    # TODO: 边界值输入
    # result = {func_short}(boundary_value)
    # assert result 符合边界预期
    pass
'''

    def _build_invariant_skeleton(self, intention: TestIntention, desc: str) -> str:
        """生成不变量测试骨架——Phase 2 由 Hypothesis 的 @given 填充。"""
        return f'''# 不变量: {desc}
# Phase 2: 用 Hypothesis @given 自动生成输入
def test_invariant_{self._safe_name(desc)}():
    """{desc}"""
    pass
'''
