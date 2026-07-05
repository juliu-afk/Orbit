"""影响面分析+候选文件. PR#201 P1-4: has_tests 修正."""
from __future__ import annotations
from typing import Any
class DesignContextBuilder:
    name = "design"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        import_deps = inputs.get("import_deps", {})
        prd = inputs.get("prd", "")
        changed = affected.get("changed", []) + affected.get("added", [])
        cross_deps = import_deps.get("cross_module_deps", {})
        candidates = []
        for f in changed[:20]:
            module = f.split("/")[1] if "/" in f and f.startswith("src/") else "root"
            deps = cross_deps.get(module, [])
            test_path = f.replace("src/", "tests/").replace(".py", "")
            candidates.append({"file": f, "module": module, "import_count": len(deps), "has_tests": any(test_path in t.replace(".py", "") for t in changed)})
        candidates.sort(key=lambda x: x.get("import_count", 0), reverse=True)
        return {"prd_summary": prd[:500] + ("..." if len(prd) > 500 else ""), "affected_modules": import_deps.get("affected_modules", []), "candidate_files": candidates[:10], "total_files": affected.get("total", 0)}
