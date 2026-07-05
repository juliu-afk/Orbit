"""合规验证 API（Step 4.3）。

GET  /api/v1/compliance/validate?domain=X&concept=Y
GET  /api/v1/compliance/validate-all?domain=X
GET  /api/v1/compliance/rules
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orbit.compliance.validator import ComplianceValidator

router = APIRouter(prefix="/compliance", tags=["compliance"])

_validator: ComplianceValidator | None = None


def _get_validator() -> ComplianceValidator:
    global _validator
    if _validator is None:
        try:
            _validator = ComplianceValidator()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"知识库不可用: {e}") from e
    return _validator


@router.get(
    "/validate",
    summary="验证知识概念合规性",
)
async def validate_concept(
    domain: str = Query(..., min_length=1),
    concept: str = Query(..., min_length=1),
) -> dict[str, Any]:
    """验证单个知识概念的合规性。"""
    v = _get_validator()
    result = v.validate(domain, concept)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"概念 {domain}/{concept} 不存在",
        )
    return result.to_dict()


@router.get(
    "/validate-all",
    summary="批量验证领域合规性",
)
async def validate_all(
    domain: str = Query("accounting", min_length=1),
) -> dict[str, Any]:
    """验证某领域所有概念的合规性。"""
    v = _get_validator()
    results = v.validate_all(domain)
    return {
        "domain": domain,
        "results": [r.to_dict() for r in results],
        "count": len(results),
    }


@router.get(
    "/rules", summary="列出合规规则"
)
async def list_rules() -> dict[str, Any]:
    """列出所有已注册的合规规则。"""
    v = _get_validator()
    return {"rules": v.list_rules(), "count": len(v.list_rules())}
