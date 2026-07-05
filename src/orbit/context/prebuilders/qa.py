"""QA——应测清单+覆盖率缺口，不跑全量."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class QAContextPrebuilder(ContextPrebuilder):
    role = "qa"
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        l2.pop("full_source", None)
        l2.pop("file_contents", None)
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            test_scope = scope.get("test_scope", "unit_integration")
            l2["test_scope"] = test_scope
            l2["test_scope_instruction"] = self._scope_instruction(test_scope)
        test_gaps = l2.get("test_gaps", {})
        if test_gaps:
            gaps = test_gaps.get("gaps", [])
            if gaps:
                l2["coverage_gap_summary"] = f"覆盖率缺口: {len(gaps)} 个文件低于 80%"
        raw_context["l2"] = l2
        return raw_context
    @staticmethod
    def _scope_instruction(test_scope: str) -> str:
        instructions = {
            "smoke": "变更仅涉及前端/非核心模块。运行冒烟测试（5 场景）。",
            "unit_integration": "变更涉及后端业务逻辑。运行单元+集成测试。",
            "full_regression": "⚠️ 变更触及核心模块。运行全量回归。",
        }
        return instructions.get(test_scope, instructions["unit_integration"])
