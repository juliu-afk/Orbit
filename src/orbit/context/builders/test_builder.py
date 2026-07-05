"""应跑测试清单."""
from __future__ import annotations
from typing import Any
class TestContextBuilder:
    name = "test"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        changed = affected.get("changed", []) + affected.get("added", [])
        scope = inputs.get("test_scope", "unit_integration")
        test_items = []
        for f in changed:
            if f.startswith("frontend/"): test_items.append({"file": f, "test_type": "vitest", "priority": "medium"})
            elif f.startswith("src/orbit/"):
                parts = f.replace("src/orbit/", "").split("/")
                module = parts[0] if parts else "root"
                test_items.append({"file": f, "test_type": "pytest", "priority": "high" if module in {"agents","scheduler","gateway","compression","hallucination"} else "medium", "test_path": f"tests/unit/test_{module}/"})
            elif f.startswith("tests/"): test_items.append({"file": f, "test_type": "self", "priority": "low"})
        priority_order = {"high": 0, "medium": 1, "low": 2}
        test_items.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 1))
        return {"test_scope": scope, "test_items": test_items, "total_tests": len(test_items), "high_priority": sum(1 for t in test_items if t.get("priority") == "high")}
