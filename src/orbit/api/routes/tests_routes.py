"""测试结果+覆盖率 API (Step 9 Phase 1.4)."""
from __future__ import annotations
import asyncio, json, os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/tests", tags=["tests"])

_workspace_dir: str | None = None

def set_workspace(d: str) -> None:
    global _workspace_dir; _workspace_dir = d

def _ws() -> str:
    if _workspace_dir is None: raise RuntimeError("workspace not set")
    return _workspace_dir

class TestCase(BaseModel):
    name: str; file: str; status: str;  # passed/failed/skipped
    duration: float; error: str | None

class TestResults(BaseModel):
    passed: int; failed: int; skipped: int; total: int
    cases: list[TestCase]

class CoverageFile(BaseModel):
    path: str; pct: float; missing_lines: list[int]


@router.get("/results", response_model=TestResults)
async def get_test_results(task_id: str | None = Query(None)):
    """运行 pytest 并返回结构化结果。task_id 可选，用于过滤测试。"""
    ws = Path(_ws())
    try:
        cmd = ["pytest", "tests/", "--json-report", "--json-report-file=/tmp/pytest_result.json", "-q", "--tb=short"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(ws),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=120.0)
        # Parse JSON report
        report_file = Path("/tmp/pytest_result.json")
        if report_file.exists():
            data = json.loads(await asyncio.to_thread(report_file.read_text, encoding="utf-8"))
            cases = []
            passed = failed = skipped = 0
            for t in data.get("tests", []):
                outcome = t.get("outcome", "unknown")
                if outcome == "passed": passed += 1
                elif outcome == "failed": failed += 1
                elif outcome == "skipped": skipped += 1
                cases.append(TestCase(
                    name=t.get("nodeid", ""),
                    file=t.get("nodeid", "").split("::")[0],
                    status=outcome,
                    duration=t.get("duration", 0),
                    error=(t.get("call", {}).get("longrepr", "")[:500] if outcome == "failed" else None),
                ))
            return TestResults(passed=passed, failed=failed, skipped=skipped, total=len(cases), cases=cases)
        return TestResults(passed=0, failed=0, skipped=0, total=0, cases=[])
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="pytest timed out (>120s)")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="pytest not found")


@router.get("/coverage", response_model=list[CoverageFile])
async def get_coverage():
    """读取 coverage.json 返回文件级覆盖率数据。"""
    ws = Path(_ws())
    cov_file = ws / "coverage.json"
    if not cov_file.exists():
        return []
    try:
        data = json.loads(await asyncio.to_thread(cov_file.read_text, encoding="utf-8"))
        files = []
        for fp, info in data.get("files", {}).items():
            summary = info.get("summary", {})
            total = summary.get("num_statements", 0)
            missing = summary.get("missing_lines", [])
            pct = round((total - len(missing)) / total * 100, 1) if total > 0 else 100
            rel = os.path.relpath(fp, ws).replace("\\", "/")
            files.append(CoverageFile(path=rel, pct=pct, missing_lines=missing))
        return sorted(files, key=lambda x: x.path)
    except Exception:
        return []
