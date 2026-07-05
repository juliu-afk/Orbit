"""Developer 上下文预构建器——编码实现阶段。

US1: Developer Agent 只收到相关代码（≤5 文件 + 现有测试）。
"""

from __future__ import annotations

from typing import Any

from orbit.context.prebuilder import ContextPrebuilder


class DeveloperContextPrebuilder(ContextPrebuilder):
    """Developer 需要变更范围 + 相关代码片段，不需要全量代码库。

    保留: prd, l2.affected_files(≤5), l2.existing_tests, artifacts.design, scope_report
    删除: l2.full_diff, 无关模块的代码片段
    注入: 代码片段限制（最多 5 个文件）
    """

    role = "developer"
    MAX_AFFECTED_FILES = 5  # 最多保留 5 个变更文件的代码片段

    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: shallow copy

        # 删除完整 diff——Developer 不需要逐行 diff，需要的是受影响文件列表
        if isinstance(l2, dict):
            l2.pop("full_diff", None)

            # 限制受影响文件列表长度
            affected = l2.get("affected_files", [])
            if isinstance(affected, list) and len(affected) > self.MAX_AFFECTED_FILES:
                remaining = len(affected) - self.MAX_AFFECTED_FILES
                l2["affected_files"] = affected[:self.MAX_AFFECTED_FILES]
                l2["affected_files_truncated"] = (
                    f"(显示前 {self.MAX_AFFECTED_FILES}/{len(affected)} 文件，"
                    f"另有 {remaining} 文件未显示)"
                )

            # 限制代码片段数量
            code_snippets = l2.get("code_snippets", [])
            if isinstance(code_snippets, list) and len(code_snippets) > self.MAX_AFFECTED_FILES:
                l2["code_snippets"] = code_snippets[:self.MAX_AFFECTED_FILES]

        # 注入变更范围摘要
        scope = raw_context.get("l2", {}).get("scope_report", {})
        if scope:
            affected_files = scope.get("affected_files", {})
            l2["scope_summary"] = (
                f"需修改 {affected_files.get('total', 0)} 文件，"
                f"测试粒度: {scope.get('test_scope', 'unknown')}"
            )

        return raw_context
