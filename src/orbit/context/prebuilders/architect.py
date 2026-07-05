"""Architect 上下文预构建器——架构设计阶段。

保留：影响面分析 + 候选文件清单 + 依赖图。丢弃：完整文件内容。
"""

from __future__ import annotations

from typing import Any

from orbit.context.prebuilder import ContextPrebuilder


class ArchitectContextPrebuilder(ContextPrebuilder):
    """Architect 需要影响面分析，不需要逐行代码。

    保留: prd, l2.file_list, l2.import_deps, scope_report, brief
    删除: l2 的完整文件内容字段（file_contents / code_context）
    注入: 影响面摘要（从 scope_report 提取）
    """

    role = "architect"

    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = raw_context.get("l2", {})

        # 删除完整文件内容——Architect 不需要逐行代码
        if isinstance(l2, dict):
            for key in ("file_contents", "code_context", "full_diff", "full_source"):
                l2.pop(key, None)

        # 注入影响面摘要（从 scope_report 提取）
        scope = raw_context.get("l2", {}).get("scope_report", {})
        if scope:
            affected = scope.get("affected_files", {})
            summary = (
                f"变更范围: {affected.get('total', 0)} 文件 "
                f"({len(affected.get('changed', []))} 修改, "
                f"{len(affected.get('added', []))} 新增, "
                f"{len(affected.get('deleted', []))} 删除)"
            )
            by_module = affected.get("by_module", {})
            if by_module:
                modules = ", ".join(
                    f"{m}({len(fs)})" for m, fs in sorted(by_module.items())
                )
                summary += f"\n按模块: {modules}"
            l2["scope_summary"] = summary

        # 依赖图（从 import_deps scanner 获取）
        import_deps = l2.get("import_deps", {})
        if import_deps:
            cross = import_deps.get("cross_module_deps", {})
            if cross:
                dep_summary = "\n".join(
                    f"- {mod}: {len(deps)} import(s)" for mod, deps in sorted(cross.items())
                )
                l2["dependency_summary"] = f"跨模块依赖:\n{dep_summary}"

        return raw_context
