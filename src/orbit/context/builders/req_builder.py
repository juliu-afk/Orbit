"""需求上下文构建器——AC 提取 + 边界条件。映射: build_requirements_input.py → requirements-input.md"""
from __future__ import annotations
from typing import Any


class RequirementsContextBuilder:
    name = "requirements"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        prd = inputs.get("prd", "")
        brief = inputs.get("brief", "")
        return {
            "prd_trimmed": prd[:3000] + ("..." if len(prd) > 3000 else ""),
            "brief_trimmed": brief[:1500] if isinstance(brief, str) else "",
            "keywords": inputs.get("keywords", []),
        }
