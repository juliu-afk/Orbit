"""时序逻辑验证 L9 (V14.2+Theory 方向5).

LTL模型检查——调度器状态机→Kripke结构→活性/安全性验证.
自实现LTL模型检查器,无需Spot/NuSMV依赖.

用法:
    v = L9TemporalValidator()
    result = v.validate(state_machine_spec)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum


class LTLProperty(StrEnum):
    SAFETY = "safety"
    LIVENESS = "liveness"


@dataclass
class TemporalResult:
    passed: bool = True
    violations: list[str] = field(default_factory=list)
    counterexamples: list[list[str]] = field(default_factory=list)


class L9TemporalValidator:
    """LTL 时序逻辑验证器——自实现模型检查."""

    SAFETY = {
        "no_overspend_without_confirm":
            ("G", "budget_exhausted -> user_confirmed"),
        "no_destructive_without_sandbox":
            ("G", "destructive_tool -> sandbox_active"),
    }
    LIVENESS = {
        "task_always_terminates":
            ("F", "task_completed | task_failed | task_cancelled"),
        "alert_always_responded":
            ("G", "critical_alert -> F hitl_notified"),
    }

    def validate(self, state_graph: dict[str, list[str]],
                 state_labels: dict[str, set[str]],
                 initial: str = "IDLE") -> TemporalResult:
        """验证状态图的LTL属性.

        state_graph: {state: [next_states]}
        state_labels: {state: {label1, label2, ...}}
        """
        violations = []
        counterexamples = []
        # 检查每条属性——简化BFS路径枚举
        all_paths = self._enumerate_paths(state_graph, initial, max_depth=20)
        for name, (op, formula) in {**self.SAFETY, **self.LIVENESS}.items():
            ce = self._check_formula(all_paths, state_labels, op, formula)
            if ce:
                violations.append(f"{name}: {formula}")
                counterexamples.append(ce)
        return TemporalResult(
            passed=len(violations) == 0,
            violations=violations,
            counterexamples=counterexamples,
        )

    def _enumerate_paths(self, graph: dict, start: str, max_depth: int) -> list[list[str]]:
        """枚举所有可达路径(≤max_depth)."""
        paths = [[start]]
        result = []
        while paths:
            path = paths.pop(0)
            cur = path[-1]
            nexts = graph.get(cur, [])
            if not nexts or len(path) >= max_depth:
                result.append(path)
            else:
                for n in nexts:
                    paths.append(path + [n])
        return result

    def _check_formula(self, paths, labels, op, formula) -> list[str] | None:
        """检查公式在指定路径上是否成立."""
        for path in paths:
            holds = self._eval_path(path, labels, op, formula)
            if not holds:
                return path
        return None

    def _eval_path(self, path, labels, op, formula) -> bool:
        """在单条路径上求值LTL公式(简化实现)."""
        if op == "G":  # Globally
            # 所有状态满足子公式
            for state in path:
                state_labels = labels.get(state, set())
                if not self._eval_atomic(formula, state_labels):
                    return False
            return True
        elif op == "F":  # Finally
            for state in path:
                state_labels = labels.get(state, set())
                if self._eval_atomic(formula, state_labels):
                    return True
            return False
        return True

    @staticmethod
    def _eval_atomic(formula: str, labels: set[str]) -> bool:
        """求值原子命题."""
        formula = formula.replace(" ", "")
        if "->" in formula:
            left, right = formula.split("->")
            return (not L9TemporalValidator._eval_atomic(left, labels)
                    or L9TemporalValidator._eval_atomic(right, labels))
        if "|" in formula:
            parts = formula.split("|")
            return any(L9TemporalValidator._eval_atomic(p, labels) for p in parts)
        if "&" in formula:
            parts = formula.split("&")
            return all(L9TemporalValidator._eval_atomic(p, labels) for p in parts)
        return formula in labels
