"""Developer——变更范围≤5文件+现有测试."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class DeveloperContextPrebuilder(ContextPrebuilder):
    role = "developer"
    MAX_AFFECTED_FILES = 5
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        affected = l2.get("affected_files", [])
        if isinstance(affected, list) and len(affected) > self.MAX_AFFECTED_FILES:
            l2["affected_files"] = affected[:self.MAX_AFFECTED_FILES]
            l2["affected_files_truncated"] = f"(显示前{self.MAX_AFFECTED_FILES}/{len(affected)})"
        code_snippets = l2.get("code_snippets", [])
        if isinstance(code_snippets, list) and len(code_snippets) > self.MAX_AFFECTED_FILES:
            l2["code_snippets"] = code_snippets[:self.MAX_AFFECTED_FILES]
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            affected_files = scope.get("affected_files", {})
            l2["scope_summary"] = f"需修改 {affected_files.get('total', 0)} 文件, 测试粒度: {scope.get('test_scope', 'unknown')}"
        raw_context["l2"] = l2
        return raw_context
