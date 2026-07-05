"""Reviewer——diff摘要+权限+schema，不含完整diff."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class ReviewerContextPrebuilder(ContextPrebuilder):
    role = "reviewer"
    DIFF_SUMMARY_MAX_CHARS = 3000
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        l2.pop("full_source", None)
        l2.pop("file_contents", None)
        diff_summary = l2.get("diff_summary", "")
        if isinstance(diff_summary, str) and len(diff_summary) > self.DIFF_SUMMARY_MAX_CHARS:
            l2["diff_summary"] = self._truncate_field(diff_summary, self.DIFF_SUMMARY_MAX_CHARS)
        if not l2.get("diff_summary"):
            affected = l2.get("affected_files", [])
            if isinstance(affected, list) and affected:
                l2["diff_summary"] = f"变更 {len(affected)} 文件: " + ", ".join(str(f) for f in affected[:10])
        perms = l2.get("permission_changes", raw_context.get("permission_changes", {}))
        if perms:
            found = perms.get("total", perms.get("permissions_found", []))
            unreg = perms.get("unregistered", [])
            l2["permission_summary"] = f"权限变更: {len(found) if isinstance(found, list) else found} 处, {len(unreg)} 处未注册" + (" ⚠️" if unreg else " ✅")
        schema = l2.get("schema_changes", raw_context.get("schema_changes", {}))
        if schema:
            parts = []
            if schema.get("tables_added"):
                parts.append(f"新增表: {', '.join(schema['tables_added'])}")
            if schema.get("tables_modified"):
                parts.append(f"修改表: {', '.join(schema['tables_modified'])}")
            if schema.get("has_migration"):
                parts.append("含数据库迁移")
            if parts:
                l2["schema_summary"] = " | ".join(parts)
        raw_context["l2"] = l2
        return raw_context
