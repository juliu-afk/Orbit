"""文档上下文构建器——需更新的文档清单。映射: build_docs_input.py → docs-input.md"""
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
                doc_updates.append(f"docs/开发计划/ 中 {f.split('/')[2] if len(f.split('/')) > 2 else 'architecture'} 相关文档")
            if f.startswith("docs/") and f != "docs/":
                doc_updates.append(f"需更新: {f}")
        return {"doc_updates": list(set(doc_updates))[:10], "note": "确定性提取——人工确认后更新"}
