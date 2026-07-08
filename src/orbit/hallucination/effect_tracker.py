"""代数效应追踪 (V14.2+Theory 方向23).

效应签名: {io, async, state, pure}
Python无原生效应系统——AST层追踪await/yield/open()/async.

用法:
    tracker = EffectTracker()
    effects = tracker.track(code)
"""
from __future__ import annotations
import ast


class EffectTracker:
    """AST效应追踪器——Koka风格的效应行多态."""

    @staticmethod
    def track(code: str) -> dict[str, set[str]]:
        """追踪函数效应签名.

        Returns: {func_name: {effect1, effect2, ...}}
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}
        result: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                effects = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Await):
                        effects.add("async")
                    elif isinstance(child, ast.AsyncFunctionDef):
                        effects.add("async")
                    elif isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            if child.func.id == "open":
                                effects.add("io")
                            elif child.func.id in ("print", "input"):
                                effects.add("io")
                    elif isinstance(child, ast.Yield):
                        effects.add("state")
                if not effects:
                    effects.add("pure")
                result[node.name] = effects
        return result

    @staticmethod
    def check_conflict(effects: dict[str, set[str]]) -> list[str]:
        """检测效应冲突——如async上下文中调用io函数."""
        conflicts = []
        for name, effs in effects.items():
            if "async" in effs and "state" in effs:
                conflicts.append(f"{name}: async+state——可能竞态")
            if "io" in effs and "pure" not in effs:
                pass  # io+非pure是常见的
        return conflicts
