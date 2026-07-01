"""L1 图谱引用验证器（Step 4.1）。

WHY L1：LLM 经常生成不存在的函数/类名。代码写完第一步就是验证引用的符号
是否在代码图谱中存在——最直接、最快速的幻觉拦截手段。

实现（ADR 技术约束）：使用 Python ast 模块（非正则）解析代码，
提取所有 Load 上下文的 Name 节点，批量查询 CodeGraphEngine.exists()。

限制（PRD Q3 决议）：仅验证静态符号（ast.Name），跳过动态属性访问
（如 obj['field']、getattr(obj, 'method')），这些留给 L2 动态追踪处理。
"""

from __future__ import annotations

import ast

import structlog

from orbit.graph.engines.code_graph import CodeGraphEngine
from orbit.hallucination.base import skip_if_empty
from orbit.hallucination.schemas import (
    HallucinationLevel,
    ValidationResult,
)

logger = structlog.get_logger("orbit.hallucination.l1")

# Python 内置名称（PRD 范围外：不验证 builtins，避免假阳性）
_BUILTINS = frozenset(
    {
        "print",
        "len",
        "range",
        "int",
        "str",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "type",
        "isinstance",
        "hasattr",
        "getattr",
        "setattr",
        "delattr",
        "super",
        "object",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "NotImplementedError",
        "StopIteration",
        "None",
        "True",
        "False",
        "open",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "any",
        "all",
        "iter",
        "next",
        "input",
        "id",
        "repr",
        "hex",
        "oct",
        "bin",
        "chr",
        "ord",
        "format",
        "pow",
        "divmod",
    }
)


class L1GraphValidator:
    """L1 代码图谱引用验证器。

    用法：
        validator = L1GraphValidator(code_engine)
        result = await validator.validate(code)
        if not result.passed:
            raise GraphReferenceError(result.metadata.get("missing_symbols", []))
    """

    def __init__(self, code_engine: CodeGraphEngine):
        self._engine = code_engine

    @skip_if_empty
    async def validate(self, code: str) -> ValidationResult:
        """验证代码中所有静态符号引用是否存在于图谱中。

        Args:
            code: LLM 生成的 Python 代码

        Returns:
            ValidationResult(passed=True) 全部存在；
            ValidationResult(passed=False) 含缺失符号列表
        """

        # 提取符号
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            # 边缘情况：语法错误代码无法解析 → 拒绝
            logger.debug("l1_syntax_error", error=str(e))
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L1_GRAPH,
                errors=[f"Syntax error in code: {e.msg} (line {e.lineno})"],
            )

        # 收集所有 Load 上下文的 Name 节点（读取引用，非定义）
        user_symbols: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
                # 跳过内置函数（PRD 范围外）
                if name not in _BUILTINS:
                    user_symbols.add(name)

        if not user_symbols:
            return ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH)

        # 批量查询图谱（一次查询一个，CodeGraphEngine 无批量接口）
        # WHY 逐个查询：当前 exists() 单条查，后续可优化为 IN 查询减少 DB 往返
        missing: list[str] = []
        for name in user_symbols:
            try:
                exists = await self._engine.exists(name)
            except Exception as e:
                # 边缘情况：图谱查询超时/异常
                logger.warning("l1_graph_query_failed", symbol=name, error=str(e))
                return ValidationResult(
                    passed=False,
                    level=HallucinationLevel.L1_GRAPH,
                    errors=[f"Graph query failed for '{name}': {e}"],
                )
            if not exists:
                missing.append(name)

        if missing:
            logger.info("l1_reference_not_found", symbols=missing)
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L1_GRAPH,
                errors=[f"Symbol not found in code graph: {', '.join(missing)}"],
                metadata={"missing_symbols": missing},
            )

        return ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH)
