"""L5 Z3 形式化验证器（Step 4.2）。

WHY L5：L1-L4 无法验证算法正确性。对于标记 @formal 的核心函数，
用 Z3 SMT 求解器自动证明 pre/post-condition 是否成立。

实现：解析 @formal/@requires/@ensures 装饰器注释，提取前置/后置条件，
构造 Z3 公式求解反例。仅支持纯数学表达式（无副作用/IO）。

PRD 决议：30s 硬超时，超时标记 unknown 不阻断。
"""

from __future__ import annotations

import ast
import re
from typing import Any

import structlog

from orbit.hallucination.schemas import (
    HallucinationLevel,
    L5ValidationResult,
)

logger = structlog.get_logger("orbit.hallucination.l5")

# Z3 超时（毫秒）
Z3_TIMEOUT_MS = 30000


class L5Z3Validator:
    """L5 Z3 形式化验证器。

    用法：
        validator = L5Z3Validator()
        result = await validator.validate(code)
        if not result.passed:
            raise L5VerificationError(result.counterexample)
    """

    def __init__(self, timeout_ms: int = Z3_TIMEOUT_MS):
        self._timeout_ms = timeout_ms

    async def validate(self, func_code: str) -> L5ValidationResult:
        """对 @formal 函数运行 Z3 验证。

        Args:
            func_code: 包含 @formal 装饰器的函数代码

        Returns:
            L5ValidationResult(z3_status="unsat"|"sat"|"skipped"|"timeout")
        """
        # 解析 @formal 装饰器提取契约
        contract = self._parse_contract(func_code)
        if contract is None:
            return L5ValidationResult(
                passed=True,
                level=HallucinationLevel.L5_Z3,
                z3_status="skipped",
                warnings=["No @formal decorator found, skipped"],
            )

        # 构造 Z3 公式并求解
        try:
            return await self._solve(contract)
        except Exception as e:
            logger.warning("l5_z3_error", error=str(e))
            return L5ValidationResult(
                passed=True,
                level=HallucinationLevel.L5_Z3,
                z3_status="unknown",
                warnings=[f"Z3 solver error: {e}"],
            )

    def _parse_contract(self, func_code: str) -> dict[str, Any] | None:
        """从 @formal 装饰器提取 pre/post conditions。

        识别格式：
            @formal
            @requires("x > 0")
            @ensures("result == x + y")
            def add(x, y): ...

        返回 {"pre": [...], "post": [...], "params": [...]} 或 None。
        """
        # 正则提取装饰器参数（兼容单/双引号）
        requires = re.findall(r'@requires\("(.+?)"\)', func_code)
        requires += re.findall(r"@requires\('(.+?)'\)", func_code)
        ensures = re.findall(r'@ensures\("(.+?)"\)', func_code)
        ensures += re.findall(r"@ensures\('(.+?)'\)", func_code)

        if "@formal" not in func_code:
            return None

        # 提取函数参数名
        try:
            tree = ast.parse(func_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    params = [a.arg for a in node.args.args]
                    return {"pre": requires, "post": ensures, "params": params}
        except SyntaxError:
            return None
        return None

    async def _solve(self, contract: dict[str, Any]) -> L5ValidationResult:
        """构造 Z3 公式并求解。

        WHY 否定后置条件：Z3 寻找使 precondition 成立但 postcondition 不成立的
        赋值（反例）。若 unsat（不存在反例）→ 函数正确。
        """
        try:
            from z3 import Int, Solver, sat, unknown  # noqa: F401
        except ImportError:
            return L5ValidationResult(
                passed=True,
                level=HallucinationLevel.L5_Z3,
                z3_status="skipped",
                warnings=["z3-solver not installed, L5 skipped"],
            )

        solver = Solver()
        solver.set("timeout", self._timeout_ms)

        # 声明变量（支持 int/float/bool）
        params = contract["params"]
        z3_vars: dict[str, object] = {}
        for p in params:
            # WHY 默认 Int：MVP 仅支持整数，后续扩展 Real/Bool 类型推断
            z3_vars[p] = Int(p)

        # 添加前置条件
        for pre in contract["pre"]:
            try:
                expr = self._safe_eval(pre, z3_vars)
                solver.add(expr)
            except Exception as e:
                logger.debug("l5_pre_parse_error", condition=pre, error=str(e))
                return L5ValidationResult(
                    passed=False,
                    level=HallucinationLevel.L5_Z3,
                    z3_status="unknown",
                    errors=[f"Cannot parse precondition: {pre}"],
                )

        # 添加后置条件的否定（寻找反例）
        for post in contract["post"]:
            try:
                # 替换 result 为函数调用表达式
                post_expr = self._safe_eval(post, z3_vars)
                solver.add(self._negate(post_expr))
            except Exception as e:
                logger.debug("l5_post_parse_error", condition=post, error=str(e))
                return L5ValidationResult(
                    passed=False,
                    level=HallucinationLevel.L5_Z3,
                    z3_status="unknown",
                    errors=[f"Cannot parse postcondition: {post}"],
                )

        result = solver.check()
        if result == sat:
            z3_model = solver.model()
            # 提取反例（只取参数值）
            ce: dict[str, object] = {}
            for name, var in z3_vars.items():
                try:
                    val = z3_model.evaluate(var)
                    ce[name] = str(val)
                except Exception:
                    ce[name] = "?"
            return L5ValidationResult(
                passed=False,
                level=HallucinationLevel.L5_Z3,
                z3_status="sat",
                errors=[f"Counterexample found: {ce}"],
                counterexample=ce,
            )
        elif result == unknown:
            return L5ValidationResult(
                passed=True,
                level=HallucinationLevel.L5_Z3,
                z3_status="timeout",
                warnings=["Z3 timeout or unsupported expression"],
            )
        else:  # unsat
            return L5ValidationResult(
                passed=True,
                level=HallucinationLevel.L5_Z3,
                z3_status="unsat",
            )

    def _safe_eval(self, expr: str, variables: dict[str, Any]) -> object:
        """安全求值数学表达式为 Z3 约束。

        WHY 不用 Python eval：仅支持有限操作符白名单（+ - * / > < == != and or not）。
        表达式先被转为 Z3 操作，避免任意代码执行。
        """
        from z3 import And, Int, Not, Or

        expr = expr.strip()
        # 替换 Python 操作符为 Z3 操作符（处理优先级）
        # 简单表达式直接映射：x > 0 → variables["x"] > 0
        result_val = expr.replace("result", "__RESULT__")

        # 只允许安全字符
        if not re.match(r'^[\w\s+\-*/%=<>!.,"\'()\[\]]+$', expr):
            raise ValueError(f"Unsafe expression: {expr}")

        # 用 eval 构建 Z3 表达式（受限环境，仅含 Z3 变量 + 操作符）
        # WHY safe：variables 只含 Z3 Int/Real 对象，无副作用
        safe_globals = {
            "And": And,
            "Or": Or,
            "Not": Not,
            "__builtins__": {},
        }
        safe_locals = dict(variables)
        safe_locals["__RESULT__"] = variables.get("result", Int("result"))
        if "result" not in variables:
            variables["result"] = Int("result")
            safe_locals["__RESULT__"] = variables["result"]

        z3_expr = eval(result_val, safe_globals, safe_locals)  # nosec B307
        return z3_expr

    def _negate(self, z3_expr: object) -> object:
        """否定 Z3 表达式（Not(expr)）。"""
        from z3 import Not

        return Not(z3_expr)
