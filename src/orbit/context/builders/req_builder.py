"""AC提取+边界."""
from __future__ import annotations
from typing import Any
class RequirementsContextBuilder:
    name = "requirements"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        prd = inputs.get("prd", ""); brief = inputs.get("brief", "")
        return {"prd_trimmed": prd[:3000] + ("..." if len(prd) > 3000 else ""), "brief_trimmed": brief[:1500] if isinstance(brief, str) else "", "keywords": inputs.get("keywords", [])}
