"""根因候选+trace."""
from __future__ import annotations
import re
from typing import Any
class DebugContextBuilder:
    name = "debug"
    def build(self, inputs: dict[str, Any]) -> dict[str, Any]:
        error = inputs.get("error", ""); traceback = inputs.get("traceback", "")
        files = list(set(re.findall(r'File "([^"]+)", line (\d+)', traceback)))
        return {"error_summary": error[:500], "candidate_files": [{"file": f, "line": int(l)} for f, l in files[:5]], "traceback_head": traceback[:2000] if len(traceback) > 2000 else traceback}
