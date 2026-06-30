"""诊断服务——运行 mypy 并解析输出。"""

from __future__ import annotations

import asyncio
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Diagnostic(BaseModel):
    file_path: str
    line: int
    column: int
    severity: DiagnosticSeverity
    message: str
    rule_id: str | None = None


class DiagnosticService:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()

    async def run_mypy(self, file_path: str) -> list[Diagnostic]:
        target = self.workspace / file_path
        if not target.exists():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                "mypy",
                "--strict",
                "--no-error-summary",
                "--show-error-codes",
                str(target),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return self._parse_mypy_output(stdout.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            return [
                Diagnostic(
                    file_path=file_path,
                    line=0,
                    column=0,
                    severity=DiagnosticSeverity.WARNING,
                    message="mypy timeout (>30s)",
                    rule_id="timeout",
                )
            ]
        except FileNotFoundError:
            return [
                Diagnostic(
                    file_path=file_path,
                    line=0,
                    column=0,
                    severity=DiagnosticSeverity.WARNING,
                    message="mypy not installed",
                    rule_id="mypy-missing",
                )
            ]

    def _parse_mypy_output(self, output: str) -> list[Diagnostic]:
        diagnostics = []
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[([\w-]+)\])?\s*$",
            re.MULTILINE,
        )
        for m in pattern.finditer(output):
            sev = {
                "error": DiagnosticSeverity.ERROR,
                "warning": DiagnosticSeverity.WARNING,
                "note": DiagnosticSeverity.INFO,
            }.get(m.group(4), DiagnosticSeverity.INFO)
            diagnostics.append(
                Diagnostic(
                    file_path=m.group(1),
                    line=int(m.group(2)),
                    column=int(m.group(3)),
                    severity=sev,
                    message=m.group(5).strip(),
                    rule_id=m.group(6),
                )
            )
        return diagnostics

    # P1-1: 并发执行避免顺序阻塞
    async def get_diagnostics(self, file_paths: list[str]) -> dict[str, list[Diagnostic]]:
        tasks = [self.run_mypy(fp) for fp in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {fp: (r if isinstance(r, list) else []) for fp, r in zip(file_paths, results)}
