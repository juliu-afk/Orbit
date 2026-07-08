"""分离逻辑验证 L10 (V14.2+Theory 方向18).

堆所有权+别名分析+Frame条件检查.
Python无指针但对象引用等效——list.append=堆写入.

用法:
    v = L10SeparationValidator()
    result = v.validate(code)
"""
from __future__ import annotations
import ast
from dataclasses import dataclass, field
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult


@dataclass
class OwnershipGraph:
    """堆所有权图——变量→引用对象集合."""
    owned: dict[str, set[str]] = field(default_factory=dict)  # func→owned_vars
    aliases: list[tuple[str, str, int]] = field(default_factory=list)  # (a,b,line)


class L10SeparationValidator:
    """分离逻辑验证——Frame条件+别名检测."""

    def validate(self, code: str) -> ValidationResult:
        errors = []
        tree = self._parse(code)
        if tree is None:
            return ValidationResult(passed=False, level=HallucinationLevel.L1_GRAPH,
                                    errors=["parse error"])
        # 1. 所有权推断
        ownership = self._infer_ownership(tree)
        # 2. Frame条件检查
        for func in self._extract_functions(tree):
            f_errors = self._check_frame(func, ownership)
            errors.extend(f_errors)
        # 3. 别名风险
        for a, b, ln in ownership.aliases:
            if self._is_risky_alias(a, b, ln, tree):
                errors.append(f"L{ln}: 风险别名——{a}和{b}共享可变对象引用")
        return ValidationResult(
            passed=len(errors) == 0,
            level=HallucinationLevel.L1_GRAPH,
            errors=errors if errors else [],
        )

    def _parse(self, code):
        try: return ast.parse(code)
        except SyntaxError: return None

    def _extract_functions(self, tree):
        return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    def _infer_ownership(self, tree) -> OwnershipGraph:
        og = OwnershipGraph()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        og.owned.setdefault("<module>", set()).add(target.id)
            # 别名: x = y (直接) 或 x = obj.y (间接,P2-4修复)
            if isinstance(node, ast.Assign):
                src_name = None
                if isinstance(node.value, ast.Name):
                    src_name = node.value.id
                elif isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                    src_name = node.value.value.id  # indirect
                if src_name:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            og.aliases.append((t.id, src_name, node.lineno))
        return og

    def _check_frame(self, func, og) -> list[str]:
        """检查函数是否篡改了参数引用的可变对象."""
        errors = []
        params = {a.arg for a in func.args.args}
        for node in ast.walk(func):
            # 参数赋值→违反frame条件
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                        if t.value.id in params:
                            errors.append(
                                f"Frame violation in {func.name} L{node.lineno}: "
                                f"修改参数 {t.value.id} 的属性——违反分离逻辑frame条件"
                            )
        return errors

    def _is_risky_alias(self, a, b, line, tree) -> bool:
        """检测风险别名——两个变量指向同一可变对象."""
        # 检查后续是否有通过任一变量的写操作
        for node in ast.walk(tree):
            if hasattr(node, 'lineno') and node.lineno > line:
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    writes = {"append", "extend", "pop", "remove", "clear", "update", "insert"}
                    if node.func.attr in writes:
                        if isinstance(node.func.value, ast.Name):
                            if node.func.value.id in (a, b):
                                return True
        return False
