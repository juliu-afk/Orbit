"""代数效应追踪 (V14.2+Theory 方向23). P1修复: stmt级过滤防嵌套泄漏."""
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
                effects = EffectTracker._scan_stmts(node.body)
                if not effects: effects.add("pure")
                result[node.name] = effects
        return result

    @staticmethod
    def _scan_stmts(body: list[ast.stmt]) -> set[str]:
        """在stmt级过滤嵌套函数——防ast.walk穿透子节点."""
        effects = set()
        for stmt in body:
            # P1修复: 跳过整个嵌套函数定义——不是continue在walk内
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for child in ast.walk(stmt):
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
