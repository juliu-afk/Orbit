"""Final batch: builders + modified core files + tests."""
import os, textwrap

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(textwrap.dedent(content).lstrip())

B = 'src/orbit/context/builders'

# ── 7 builders ──
w(f'{B}/__init__.py', '"""Context Builder——映射 Token 节省报告 Phase 2 的 7 个脚本."""\n')

w(f'{B}/test_builder.py', '''
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
''')

w(f'{B}/design_builder.py', '''
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
''')

w(f'{B}/impl_builder.py', '''
"""最小变更任务书."""
from __future__ import annotations
from typing import Any
class ImplementationContextBuilder:
    name = "implementation"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        tasks = [{"file": f, "action": "modify" if f in affected.get("changed", []) else "create"} for f in affected.get("changed", []) + affected.get("added", [])]
        return {"tasks": tasks[:15], "total_files": len(tasks)}
''')

w(f'{B}/debug_builder.py', '''
"""根因候选+trace."""
from __future__ import annotations
import re
from typing import Any
class DebugContextBuilder:
    name = "debug"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        error = inputs.get("error", ""); traceback = inputs.get("traceback", "")
        files = list(set(re.findall(r'File "([^"]+)", line (\\d+)', traceback)))
        return {"error_summary": error[:500], "candidate_files": [{"file": f, "line": int(l)} for f, l in files[:5]], "traceback_head": traceback[:2000] if len(traceback) > 2000 else traceback}
''')

w(f'{B}/req_builder.py', '''
"""AC提取+边界."""
from __future__ import annotations
from typing import Any
class RequirementsContextBuilder:
    name = "requirements"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        prd = inputs.get("prd", ""); brief = inputs.get("brief", "")
        return {"prd_trimmed": prd[:3000] + ("..." if len(prd) > 3000 else ""), "brief_trimmed": brief[:1500] if isinstance(brief, str) else "", "keywords": inputs.get("keywords", [])}
''')

w(f'{B}/docs_builder.py', '''
"""需更新的文档清单."""
from __future__ import annotations
from typing import Any
class DocsContextBuilder:
    name = "docs"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {})
        all_files = affected.get("changed", []) + affected.get("added", [])
        doc_updates = []
        for f in all_files:
            if f.startswith("src/orbit/"):
                parts = f.split("/")
                doc_updates.append(f"docs/开发计划/ {parts[2] if len(parts) > 2 else 'architecture'} 相关文档")
            if f.startswith("docs/") and f != "docs/":
                doc_updates.append(f"需更新: {f}")
        return {"doc_updates": list(set(doc_updates))[:10], "note": "确定性提取——人工确认后更新"}
''')

w(f'{B}/release_builder.py', '''
"""release notes+风险清单."""
from __future__ import annotations
from typing import Any
class ReleaseContextBuilder:
    name = "release"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        affected = inputs.get("affected_files", {}); scope = inputs.get("test_scope", "unit_integration")
        risks = []
        if scope == "full_regression": risks.append("⚠️ 触及核心模块——需全量回归+手动验收")
        schema = inputs.get("schema_changes", {}); perms = inputs.get("permission_changes", {})
        if schema.get("has_migration"): risks.append("⚠️ 含数据库迁移——需备份+回滚方案")
        if perms.get("unregistered"): risks.append(f"⚠️ {len(perms['unregistered'])} 处未注册权限字符串")
        return {"file_count": affected.get("total", 0), "modules": list(affected.get("by_module", {}).keys()), "test_scope": scope, "risks": risks, "migration_needed": schema.get("has_migration", False)}
''')

print("Builders done")
