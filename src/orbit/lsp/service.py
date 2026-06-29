"""诊断服务——运行 mypy/ruff 并解析输出为标准 Diagnostic。

WHY subprocess mypy 而非直接调用 API：mypy 的 daemon 模式不稳定，
子进程模式隔离性好，超时可控。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CodeAction(BaseModel):
    """快速修复建议（Phase 2 启用）。"""
    title: str
    kind: str = "quickfix"
    edit: str | None = None  # 替换文本


class Diagnostic(BaseModel):
    file_path: str
    line: int
    column: int
    severity: DiagnosticSeverity
    message: str
    rule_id: str | None = None
    fix: CodeAction | None = None


class DiagnosticService:
    """诊断服务——对 workspace 中变更文件运行 mypy。

    超时 30s，超时不阻塞审查流程。
    """

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()

    async def run_mypy(self, file_path: str) -> list[Diagnostic]:
        """对单个文件运行 mypy --strict。

        WHY --strict：与防幻觉 L4 的 mypy --strict 保持一致，
        确保前端诊断与 Agent 验证用同一套规则。
        """
        target = self.workspace / file_path
        if not target.exists():
            return []

        try:
            proc = await asyncio.create_subprocess_exec(
                "mypy", "--strict", "--no-error-summary",
                "--show-error-codes", str(target),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return self._parse_mypy_output(stdout.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            return [Diagnostic(
                file_path=file_path, line=0, column=0,
                severity=DiagnosticSeverity.WARNING,
                message="mypy 检查超时（>30s），请手动运行 mypy",
                rule_id="timeout",
            )]
        except FileNotFoundError:
            return [Diagnostic(
                file_path=file_path, line=0, column=0,
                severity=DiagnosticSeverity.WARNING,
                message="mypy 未安装，诊断不可用",
                rule_id="mypy-missing",
            )]

    def _parse_mypy_output(self, output: str) -> list[Diagnostic]:
        """解析 mypy 输出为标准 Diagnostic。

        mypy 格式: file:line:col: severity: message  [error-code]
        """
        diagnostics = []
        # mypy 输出格式：file:line:col: error: message  [code]
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[([\w-]+)\])?\s*$",
            re.MULTILINE,
        )
        for m in pattern.finditer(output):
            sev = m.group(4)
            severity = {
                "error": DiagnosticSeverity.ERROR,
                "warning": DiagnosticSeverity.WARNING,
                "note": DiagnosticSeverity.INFO,
            }.get(sev, DiagnosticSeverity.INFO)
            diagnostics.append(Diagnostic(
                file_path=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=severity,
                message=m.group(5).strip(),
                rule_id=m.group(6),
            ))
        return diagnostics

    async def get_diagnostics(self, file_paths: list[str]) -> dict[str, list[Diagnostic]]:
        """批量获取诊断结果。"""
        results = {}
        for fp in file_paths:
            results[fp] = await self.run_mypy(fp)
        return results
