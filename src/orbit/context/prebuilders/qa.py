"""QA 上下文预构建器——测试验证阶段。

US4: QA Agent 只跑增量测试——根据变更范围决定测试粒度。
"""

from __future__ import annotations

from typing import Any

from orbit.context.prebuilder import ContextPrebuilder


class QAContextPrebuilder(ContextPrebuilder):
    """QA 需要应测清单 + 覆盖率缺口，不需要完整 diff。

    保留: prd, l2.affected_files, l2.test_gaps, l2.scope_report, artifacts
    删除: l2.full_diff, l2.full_source
    注入: 测试粒度决策 + 应测清单
    """

    role = "qa"

    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: shallow copy

        if isinstance(l2, dict):
            # 删除完整代码——QA 不需要逐行阅读
            l2.pop("full_diff", None)
            l2.pop("full_source", None)
            l2.pop("file_contents", None)

            # 注入测试粒度决策（从 scope_report 提取）
            scope = raw_context.get("l2", {}).get("scope_report", {})
            if scope:
                test_scope = scope.get("test_scope", "unit_integration")
                l2["test_scope"] = test_scope
                l2["test_scope_instruction"] = self._scope_instruction(test_scope)

            # 注入覆盖率缺口提示
            test_gaps = l2.get("test_gaps", {})
            if test_gaps:
                gaps = test_gaps.get("gaps", [])
                if gaps:
                    l2["coverage_gap_summary"] = (
                        f"覆盖率缺口: {len(gaps)} 个文件低于 80%——"
                        + ", ".join(g.get("file", "?") for g in gaps[:5])
                        + ("..." if len(gaps) > 5 else "")
                    )

        return raw_context

    @staticmethod
    def _scope_instruction(test_scope: str) -> str:
        """测试粒度 → 具体执行指令。"""
        instructions = {
            "smoke": (
                "变更仅涉及前端/非核心模块。"
                "运行冒烟测试（5 场景）即可——pytest tests/e2e/ -q -k 'smoke'"
            ),
            "unit_integration": (
                "变更涉及后端业务逻辑。"
                "运行单元测试 + 集成测试——pytest tests/unit/ tests/integration/ -q"
            ),
            "full_regression": (
                "⚠️ 变更触及核心模块（agents/scheduler/gateway/compression/hallucination）。"
                "运行全量回归——pytest tests/unit/ tests/integration/ tests/e2e/ -q"
            ),
        }
        return instructions.get(test_scope, instructions["unit_integration"])
