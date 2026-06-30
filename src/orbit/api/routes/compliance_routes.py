"""合规检查 API (Phase 3.2)——Diff 合规标注+审查清单自动生成."""

from __future__ import annotations
import ast, re
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/compliance", tags=["compliance_check"])  # P2-4: 区分旧 compliance 模块

_file_service = None


def set_file_service(svc) -> None:
    global _file_service
    _file_service = svc


class ComplianceViolation(BaseModel):
    file: str
    line: int
    rule: str
    message: str
    severity: str


class ReviewChecklist(BaseModel):
    items: list[dict[str, str]]


RULES = [
    # P2-1: 限制 float 匹配范围——排除 "floatValue"/"my_float" 等变量名
    (
        "float-instead-of-decimal",
        "金额字段可能用了 float，应用 Decimal",
        "warning",
        r"(?:^|\s|=|\(|\[)\s*float\s*[=\(]",
    ),
    # P1-1: 改为正向检查——匹配 @router 装饰器的那行，后续 AST 做缺失检查
    (
        "router-endpoint",
        "发现路由端点，检查是否有 @require_permission",
        "info",
        r"@router\.(?:get|post|put|delete|patch)\(",
    ),
    # P2-2: 限制 SQL 匹配范围，排除日志字符串和 ORM 相关
    (
        "direct-sql",
        "发现 SQL 关键词，检查是否直接写 SQL",
        "info",
        r"(?:execute|executescript|raw_query)\s*\(",
    ),
]


@router.get("/check")
async def compliance_check(file: str = Query(...)):
    """扫描文件返回合规违规标注."""
    if not _file_service:
        raise HTTPException(status_code=503)
    try:
        content = await _file_service.read_file(file)
    except Exception:
        raise HTTPException(status_code=404)
    violations = []
    for rule_id, msg, severity, pattern in RULES:
        for lineno, line in enumerate(content.split("\n"), 1):
            if re.search(pattern, line, re.IGNORECASE):
                violations.append(
                    ComplianceViolation(
                        file=file,
                        line=lineno,
                        rule=rule_id,
                        message=msg,
                        severity=severity,
                    )
                )
    return {"violations": [v.model_dump() for v in violations[:50]]}


@router.get("/checklist")
async def review_checklist(task_type: str = Query("core")):
    """根据改动类型生成审查清单."""
    items = {
        "core": [
            {"check": "借贷平衡", "rule": "debit == credit"},
            {"check": "金额字段 Decimal", "rule": "no float/int for money"},
            {"check": "权限装饰器", "rule": "@require_permission on new endpoints"},
        ],
        "frontend": [
            {"check": "TypeScript strict", "rule": "no any/as assertions"},
            {"check": "组件 <200 行", "rule": "single responsibility"},
        ],
        "default": [
            {"check": "测试覆盖", "rule": "≥1 integration test per endpoint"},
            {"check": "异常处理", "rule": "no bare except Exception"},
        ],
    }
    return {"items": items.get(task_type, items["default"])}
