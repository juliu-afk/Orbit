"""设计上下文构建器——影响面分析 + 候选文件。

映射: build_design_input.py → design-input.md
"""

from __future__ import annotations

from typing import Any


class DesignContextBuilder:
    """PRD + 代码图谱 → 影响面 + 候选文件。不用 LLM。"""

    name = "design"

    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        import_deps = inputs.get("import_deps", {})
        prd = inputs.get("prd", "")

        # 候选文件——按受影响程度排序
        candidates: list[dict[str, Any]] = []
        changed = affected.get("changed", []) + affected.get("added", [])
        cross_deps = import_deps.get("cross_module_deps", {})

        for f in changed[:20]:  # 最多 20 个
            module = f.split("/")[1] if "/" in f and f.startswith("src/") else "root"
            deps = cross_deps.get(module, [])
            candidates.append({
                "file": f,
                "module": module,
                "import_count": len(deps),
                "has_tests": any(
                    # f → test path: "src/orbit/agents/x.py" → "tests/orbit/agents/x"
                    f.replace("src/", "tests/").replace(".py", "") in t.replace(".py", "")
                    for t in changed
                ),
            })

        # 按 import 数量排序——import 多的文件影响面大
        candidates.sort(key=lambda x: x.get("import_count", 0), reverse=True)

        return {
            "prd_summary": prd[:500] + ("..." if len(prd) > 500 else ""),
            "affected_modules": import_deps.get("affected_modules", []),
            "candidate_files": candidates[:10],
            "total_files": affected.get("total", 0),
        }
