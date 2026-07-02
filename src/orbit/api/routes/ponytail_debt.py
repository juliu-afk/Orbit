"""Ponytail 债务台账 API。

扫描项目代码中的 `# ponytail:` 注释，聚合为技术债务台账。
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, status

from orbit.projects.registry import ProjectRegistry

logger = structlog.get_logger("orbit.api.ponytail_debt")

router = APIRouter(prefix="/projects", tags=["ponytail-debt"])

_registry = ProjectRegistry()

# ── 扫描逻辑 ──────────────────────────────────────────────

# Ponytail 注释格式: # ponytail: <天花板> — 升级触发: <条件>
# 也支持: // ponytail: , <!-- ponytail: -->
PONYTAIL_PATTERN = re.compile(
    r"(?:#|//|<!--)\s*ponytail:\s*(.+?)"
    r"(?:\s*(?:—|--|-)\s*(?:升级触发|upgrade\s*when|trigger)[：:\s]+(.+?))?"
    r"(?:\s*-->)?$",
    re.IGNORECASE,
)

IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build",
               "dist", "target", ".orbit", "data", "Deliverables", ".next", ".turbo"}


def _scan_ponytail_comments(project_path: str) -> list[dict]:
    """扫描项目中所有 ponytail: 注释。

    Returns:
        [{file, line, ceiling, trigger, raw}] 列表
    """
    entries: list[dict] = []
    root = Path(project_path)
    if not root.is_dir():
        return entries

    for dirpath, dirnames, filenames in os.walk(project_path):
        # 跳过忽略目录
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for fname in filenames:
            # 只扫描代码文件
            if not _is_code_file(fname):
                continue
            filepath = Path(dirpath) / fname
            try:
                content = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for i, line in enumerate(content.split("\n"), 1):
                match = PONYTAIL_PATTERN.search(line)
                if match:
                    ceiling = match.group(1).strip() if match.group(1) else ""
                    trigger = match.group(2).strip() if match.group(2) else ""
                    entries.append({
                        "file": str(filepath.relative_to(root)).replace("\\", "/"),
                        "line": i,
                        "ceiling": ceiling,
                        "trigger": trigger,
                        "raw": line.strip(),
                    })

    return entries


def _is_code_file(filename: str) -> bool:
    """检查是否为可扫描的代码文件。"""
    code_extensions = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
        ".kt", ".swift", ".c", ".cpp", ".h", ".rb", ".php", ".vue", ".svelte",
    }
    return any(filename.endswith(ext) for ext in code_extensions)


# ── API 端点 ─────────────────────────────────────────────


@router.get(
    "/{name}/ponytail-debt",
    response_model=dict,
    summary="查询 Ponytail 债务台账",
    description="扫描项目中所有 ponytail: 注释，聚合为技术债务台账。",
    responses={404: {"description": "项目不存在"}},
)
async def get_ponytail_debt(name: str) -> dict:
    project = _registry.get(name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "detail": f"项目 {name} 不存在",
                "error_code": "PROJECT_NOT_FOUND",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    entries = _scan_ponytail_comments(project.local_path)

    # 按天花板分类
    by_ceiling: dict[str, int] = {}
    for e in entries:
        ceiling = e["ceiling"] or "未分类"
        by_ceiling[ceiling] = by_ceiling.get(ceiling, 0) + 1

    # 有升级触发条件的（可立即升级的）
    actionable = [e for e in entries if e["trigger"]]

    return {
        "code": 0,
        "data": {
            "project_name": name,
            "total": len(entries),
            "by_ceiling": by_ceiling,
            "actionable_count": len(actionable),
            "entries": entries[:100],  # 最多返回 100 条
        },
        "message": "ok",
    }
