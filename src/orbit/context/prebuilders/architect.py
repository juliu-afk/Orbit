"""Architect——影响面+候选文件，不要完整代码."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class ArchitectContextPrebuilder(ContextPrebuilder):
    role = "architect"
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        for key in ("file_contents", "code_context", "full_diff", "full_source"):
            l2.pop(key, None)
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            affected = scope.get("affected_files", {})
            by_module = affected.get("by_module", {})
            summary = f"变更范围: {affected.get('total', 0)} 文件"
            if by_module:
                modules = ", ".join(f"{m}({len(fs)})" for m, fs in sorted(by_module.items()))
                summary += f"\n按模块: {modules}"
            l2["scope_summary"] = summary
        import_deps = l2.get("import_deps", {})
        if import_deps:
            cross = import_deps.get("cross_module_deps", {})
            if cross:
                l2["dependency_summary"] = "跨模块依赖:\n" + "\n".join(
                    f"- {mod}: {len(deps)} import(s)" for mod, deps in sorted(cross.items())
                )
        raw_context["l2"] = l2
        return raw_context
