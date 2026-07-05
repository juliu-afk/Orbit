"""调试上下文构建器——根因候选 + trace 路径。映射: build_debug_input.py → debug-input.md"""
from __future__ import annotations
from typing import Any


class DebugContextBuilder:
    name = "debug"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        error = inputs.get("error", "")
        traceback = inputs.get("traceback", "")
        # 提取文件名 + 行号
        import re
        files = list(set(re.findall(r'File "([^"]+)", line (\d+)', traceback)))
        return {
            "error_summary": error[:500],
            "candidate_files": [{"file": f, "line": int(l)} for f, l in files[:5]],
            "traceback_head": traceback[:2000] if len(traceback) > 2000 else traceback,
        }
