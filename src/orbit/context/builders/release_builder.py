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
