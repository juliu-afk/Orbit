"""实现上下文构建器——最小变更任务书。

映射: build_implementation_input.py → implementation-input.md
"""

from __future__ import annotations

from typing import Any


class ImplementationContextBuilder:
    """技术方案 + 代码图谱 → 最小变更任务书。不用 LLM。"""

    name = "implementation"

    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        design = inputs.get("design", {})

        tasks: list[dict[str, Any]] = []
        for f in affected.get("changed", []) + affected.get("added", []):
            action = "modify" if f in affected.get("changed", []) else "create"
            tasks.append({"file": f, "action": action})

        return {
            "tasks": tasks[:15],
            "total_files": len(tasks),
            "design_summary": str(design.get("summary", ""))[:1000],
        }
