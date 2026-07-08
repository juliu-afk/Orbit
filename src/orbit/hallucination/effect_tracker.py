"""代数效应追踪 (V14.2+Theory 方向23). P1修复: 仅遍历顶层函数体非嵌套."""
from __future__ import annotations
import ast

class EffectTracker:
    @staticmethod
    def track(code: str) -> dict[str, set[str]]:
        try: tree = ast.parse(code)
        except SyntaxError: return {}
        result = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                effects = EffectTracker._scan_body(node.body)
                if not effects: effects.add("pure")
                result[node.name] = effects
        return result

    @staticmethod
    def _scan_body(body: list[ast.stmt]) -> set[str]:
        """仅扫描直接子节点——不穿透嵌套函数."""
        effects = set()
        for stmt in body:
            for child in ast.walk(stmt):
                # 遇到嵌套函数/类→不穿透
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(child, ast.Await):
                    effects.add("async")
                elif isinstance(child, ast.Yield) or isinstance(child, ast.YieldFrom):
                    effects.add("state")
                elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id in ("open", "print", "input"):
                        effects.add("io")
        return effects

    @staticmethod
    def check_conflict(effects: dict[str, set[str]]) -> list[str]:
        conflicts = []
        for name, effs in effects.items():
            if "async" in effs and "state" in effs:
                conflicts.append(f"{name}: async+state——可能竞态")
        return conflicts
