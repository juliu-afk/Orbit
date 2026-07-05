"""Reviewer 上下文预构建器——代码审查阶段。

US2: Reviewer Agent 不收到完整 diff——只有 diff 摘要 + 权限变更 + schema 变更。
类比 Token 节省报告 build_reviewer_input.py：reviewer-input.md 不含完整 diff。
"""

from __future__ import annotations

from typing import Any

from orbit.context.prebuilder import ContextPrebuilder


class ReviewerContextPrebuilder(ContextPrebuilder):
    """Reviewer 需要高风险点摘要，不需要逐行 diff。

    保留: prd, l2.diff_summary(≤3000), l2.permission_changes, l2.schema_changes, artifacts
    删除: l2.full_diff, l2.full_source
    注入: diff 摘要（规范化后 ≤3000 chars）
    """

    role = "reviewer"
    DIFF_SUMMARY_MAX_CHARS = 3000  # 报告 reviewer-input.md 级别

    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = raw_context.get("l2", {})

        if isinstance(l2, dict):
            # ★ 核心：删除完整 diff
            l2.pop("full_diff", None)
            l2.pop("full_source", None)
            l2.pop("file_contents", None)

            # 如果有 diff_summary，截断到 3000 chars
            diff_summary = l2.get("diff_summary", "")
            if isinstance(diff_summary, str) and len(diff_summary) > self.DIFF_SUMMARY_MAX_CHARS:
                l2["diff_summary"] = self._truncate_field(diff_summary, self.DIFF_SUMMARY_MAX_CHARS)

            # 如果没有 diff_summary，从其他字段构建摘要
            if not l2.get("diff_summary") and "affected_files" in l2:
                affected = l2.get("affected_files", [])
                if isinstance(affected, list):
                    l2["diff_summary"] = (
                        f"变更 {len(affected)} 文件: "
                        + ", ".join(str(f) for f in affected[:10])
                        + ("..." if len(affected) > 10 else "")
                    )

            # 注入权限变更摘要
            perms = l2.get("permission_changes", {})
            if perms:
                found = perms.get("permissions_found", [])
                unreg = perms.get("unregistered", [])
                l2["permission_summary"] = (
                    f"权限变更: {len(found)} 处权限字符串, "
                    f"{len(unreg)} 处未注册" + (" ⚠️" if unreg else " ✅")
                )

            # 注入 schema 变更摘要
            schema = l2.get("schema_changes", {})
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

        # 保留 artifacts——Reviewer 需要看前序 Agent 产出
        return raw_context
