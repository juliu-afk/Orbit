"""Build all remaining Phase 2 files with PR#201 fixes."""
import os, textwrap

BASE = 'src/orbit/context'

def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(textwrap.dedent(content).lstrip())

# ── prebuilder.py (P2-1 cached, P2-2 chatter→clarifier) ──
w(f'{BASE}/prebuilder.py', '''
"""ContextPrebuilder 基类 + 工厂 (Phase 2 Token节省, PR#201 审查修复)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class ContextPrebuilder(ABC):
    role: str = ""
    max_chars_per_field: int = 5000

    @abstractmethod
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]: ...

    def _truncate_field(self, value: str, max_chars: int | None = None) -> str:
        limit = max_chars or self.max_chars_per_field
        if len(value) <= limit:
            return value
        half = limit // 2
        cut = len(value) - limit
        return value[:half] + f"\\n... [{cut} chars truncated] ...\\n" + value[-half:]

    def _strip_keys(self, d: dict[str, Any], keys_to_remove: set[str]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k not in keys_to_remove}

    # PR#201 P2-1: 模块级缓存——Prebuilder 无状态
    _instances: dict[str, "ContextPrebuilder"] = {}

    @staticmethod
    def build_for_role(role: str) -> "ContextPrebuilder":
        if role in ContextPrebuilder._instances:
            return ContextPrebuilder._instances[role]
        from orbit.context.prebuilders.architect import ArchitectContextPrebuilder
        from orbit.context.prebuilders.clarifier import ClarifierContextPrebuilder
        from orbit.context.prebuilders.developer import DeveloperContextPrebuilder
        from orbit.context.prebuilders.qa import QAContextPrebuilder
        from orbit.context.prebuilders.reviewer import ReviewerContextPrebuilder
        mapping: dict[str, ContextPrebuilder] = {
            "clarifier": ClarifierContextPrebuilder(),
            "architect": ArchitectContextPrebuilder(),
            "developer": DeveloperContextPrebuilder(),
            "reviewer": ReviewerContextPrebuilder(),
            "qa": QAContextPrebuilder(),
            "chatter": ClarifierContextPrebuilder(),  # PR#201 P2-2: chatter→clarifier
        }
        instance = mapping.get(role, DeveloperContextPrebuilder())
        ContextPrebuilder._instances[role] = instance
        return instance
''')

# ── 5 prebuilders (P1-5 shallow copy fixed) ──
w(f'{BASE}/prebuilders/__init__.py', '"""角色特定 ContextPrebuilder 子类 (Phase 2 Token节省)."""\n')

w(f'{BASE}/prebuilders/clarifier.py', '''
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
''')

w(f'{BASE}/prebuilders/architect.py', '''
"""Architect——影响面+候选文件，不要完整代码."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class ArchitectContextPrebuilder(ContextPrebuilder):
    role = "architect"
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        for key in ("file_contents", "code_context", "full_diff", "full_source"):
            l2.pop(key, None)
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            affected = scope.get("affected_files", {})
            by_module = affected.get("by_module", {})
            summary = f"变更范围: {affected.get('total', 0)} 文件"
            if by_module:
                modules = ", ".join(f"{m}({len(fs)})" for m, fs in sorted(by_module.items()))
                summary += f"\\n按模块: {modules}"
            l2["scope_summary"] = summary
        import_deps = l2.get("import_deps", {})
        if import_deps:
            cross = import_deps.get("cross_module_deps", {})
            if cross:
                l2["dependency_summary"] = "跨模块依赖:\\n" + "\\n".join(
                    f"- {mod}: {len(deps)} import(s)" for mod, deps in sorted(cross.items())
                )
        raw_context["l2"] = l2
        return raw_context
''')

w(f'{BASE}/prebuilders/developer.py', '''
"""Developer——变更范围≤5文件+现有测试."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class DeveloperContextPrebuilder(ContextPrebuilder):
    role = "developer"
    MAX_AFFECTED_FILES = 5
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        affected = l2.get("affected_files", [])
        if isinstance(affected, list) and len(affected) > self.MAX_AFFECTED_FILES:
            l2["affected_files"] = affected[:self.MAX_AFFECTED_FILES]
            l2["affected_files_truncated"] = f"(显示前{self.MAX_AFFECTED_FILES}/{len(affected)})"
        code_snippets = l2.get("code_snippets", [])
        if isinstance(code_snippets, list) and len(code_snippets) > self.MAX_AFFECTED_FILES:
            l2["code_snippets"] = code_snippets[:self.MAX_AFFECTED_FILES]
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            affected_files = scope.get("affected_files", {})
            l2["scope_summary"] = f"需修改 {affected_files.get('total', 0)} 文件, 测试粒度: {scope.get('test_scope', 'unknown')}"
        raw_context["l2"] = l2
        return raw_context
''')

w(f'{BASE}/prebuilders/reviewer.py', '''
"""Reviewer——diff摘要+权限+schema，不含完整diff."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class ReviewerContextPrebuilder(ContextPrebuilder):
    role = "reviewer"
    DIFF_SUMMARY_MAX_CHARS = 3000
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        l2.pop("full_source", None)
        l2.pop("file_contents", None)
        diff_summary = l2.get("diff_summary", "")
        if isinstance(diff_summary, str) and len(diff_summary) > self.DIFF_SUMMARY_MAX_CHARS:
            l2["diff_summary"] = self._truncate_field(diff_summary, self.DIFF_SUMMARY_MAX_CHARS)
        if not l2.get("diff_summary"):
            affected = l2.get("affected_files", [])
            if isinstance(affected, list) and affected:
                l2["diff_summary"] = f"变更 {len(affected)} 文件: " + ", ".join(str(f) for f in affected[:10])
        perms = l2.get("permission_changes", raw_context.get("permission_changes", {}))
        if perms:
            found = perms.get("total", perms.get("permissions_found", []))
            unreg = perms.get("unregistered", [])
            l2["permission_summary"] = f"权限变更: {len(found) if isinstance(found, list) else found} 处, {len(unreg)} 处未注册" + (" ⚠️" if unreg else " ✅")
        schema = l2.get("schema_changes", raw_context.get("schema_changes", {}))
        if schema:
            parts = []
            if schema.get("tables_added"):
                parts.append(f"新增表: {', '.join(schema['tables_added'])}")
            if schema.get("tables_modified"):
                parts.append(f"修改表: {', '.join(schema['tables_modified'])}")
            if schema.get("has_migration"):
                parts.append("含数据库迁移")
            if parts:
                l2["schema_summary"] = " | ".join(parts)
        raw_context["l2"] = l2
        return raw_context
''')

w(f'{BASE}/prebuilders/qa.py', '''
"""QA——应测清单+覆盖率缺口，不跑全量."""
from __future__ import annotations
from typing import Any
from orbit.context.prebuilder import ContextPrebuilder

class QAContextPrebuilder(ContextPrebuilder):
    role = "qa"
    def build(self, raw_context: dict[str, Any]) -> dict[str, Any]:
        l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: 浅拷贝避免副作用
        l2.pop("full_diff", None)
        l2.pop("full_source", None)
        l2.pop("file_contents", None)
        scope = l2.get("scope_report", raw_context.get("scope_report", {}))
        if scope:
            test_scope = scope.get("test_scope", "unit_integration")
            l2["test_scope"] = test_scope
            l2["test_scope_instruction"] = self._scope_instruction(test_scope)
        test_gaps = l2.get("test_gaps", {})
        if test_gaps:
            gaps = test_gaps.get("gaps", [])
            if gaps:
                l2["coverage_gap_summary"] = f"覆盖率缺口: {len(gaps)} 个文件低于 80%"
        raw_context["l2"] = l2
        return raw_context
    @staticmethod
    def _scope_instruction(test_scope: str) -> str:
        instructions = {
            "smoke": "变更仅涉及前端/非核心模块。运行冒烟测试（5 场景）。",
            "unit_integration": "变更涉及后端业务逻辑。运行单元+集成测试。",
            "full_regression": "⚠️ 变更触及核心模块。运行全量回归。",
        }
        return instructions.get(test_scope, instructions["unit_integration"])
''')

print("Prebuilders done")
