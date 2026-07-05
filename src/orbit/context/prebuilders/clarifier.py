"""Clarifier——只给需求，不给代码."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class ClarifierContextPrebuilder(ContextPrebuilder):
    role = "clarifier"
    PRD_MAX_CHARS = 3000
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        stripped = self._strip_keys(raw_context, {"l2"})
        l3 = stripped.get("l3", {})
        if isinstance(l3, dict) and "prd" in l3:
            l3["prd"] = self._truncate_field(str(l3["prd"]), self.PRD_MAX_CHARS)
        brief = stripped.get("brief", "")
        if isinstance(brief, str):
            stripped["brief"] = self._truncate_field(brief, 2000)
        return stripped
