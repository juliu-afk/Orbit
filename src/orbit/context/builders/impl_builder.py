"""最小变更任务书."""
from __future__ import annotations
from typing import Any
class ImplementationContextBuilder:
    name = "implementation"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        tasks = [{"file": f, "action": "modify" if f in affected.get("changed", []) else "create"} for f in affected.get("changed", []) + affected.get("added", [])]
        return {"tasks": tasks[:15], "total_files": len(tasks)}
