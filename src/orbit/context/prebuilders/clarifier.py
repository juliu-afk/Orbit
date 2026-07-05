"""Clarifier 上下文预构建器——需求澄清阶段。

US5: Clarifier Agent 不看到代码细节——只给用户输入+项目说明书+关键词。
"""

from __future__ import annotations

from typing import Any

from orbit.context.prebuilder import ContextPrebuilder


class ClarifierContextPrebuilder(ContextPrebuilder):
    """Clarifier 只看到需求，不看到代码实现。

    删除: l2(代码图谱), artifacts(历史产物), scope_report
    保留: prd, brief, keywords, l1(宪法)
    """

    role = "clarifier"
    # Clarifier 不需要完整 PRD——截断到 3000 chars
    PRD_MAX_CHARS = 3000

    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        # 删除代码相关字段
        stripped = self._strip_keys(raw_context, {
            "l2",           # 四图谱——Clarifier 不需要代码细节
        })

        # 截断 PRD 到较短长度——需求理解不需要完整 5000 字
        l3 = stripped.get("l3", {})
        if isinstance(l3, dict) and "prd" in l3:
            l3["prd"] = self._truncate_field(str(l3["prd"]), self.PRD_MAX_CHARS)

        # 保留项目说明书（brief）——帮助理解项目背景
        brief = stripped.get("brief", "")
        if isinstance(brief, str):
            stripped["brief"] = self._truncate_field(brief, 2000)

        return stripped
