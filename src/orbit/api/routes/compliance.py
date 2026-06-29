"""ÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂ APIÃÂ¯ÃÂ¼ÃÂStep 4.3ÃÂ¯ÃÂ¼ÃÂÃÂ£ÃÂÃÂ

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
    summary="ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ§ÃÂÃÂ¥ÃÂ¨ÃÂ¯ÃÂÃÂ¦ÃÂ¦ÃÂÃÂ¥ÃÂ¿ÃÂµÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¦ÃÂÃÂ§",
)
async def validate_concept(
    domain: str = Query(..., min_length=1),
    concept: str = Query(..., min_length=1),
) -> dict[str, Any]:
    """ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¥ÃÂÃÂÃÂ¤ÃÂ¸ÃÂªÃÂ§ÃÂÃÂ¥ÃÂ¨ÃÂ¯ÃÂÃÂ¦ÃÂ¦ÃÂÃÂ¥ÃÂ¿ÃÂµÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¦ÃÂÃÂ§ÃÂ£ÃÂÃÂ"""
    v = _get_validator()
    result = v.validate(domain, concept)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"ÃÂ¦ÃÂ¦ÃÂÃÂ¥ÃÂ¿ÃÂµ {domain}/{concept} ÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¥ÃÂÃÂ¨",
        )
    return result.to_dict()


@router.get(
    "/validate-all",
    summary="ÃÂ¦ÃÂÃÂ¹ÃÂ©ÃÂÃÂÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ©ÃÂ¢ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¦ÃÂÃÂ§",
)
async def validate_all(
    domain: str = Query("accounting", min_length=1),
) -> dict[str, Any]:
    """ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¦ÃÂÃÂÃÂ©ÃÂ¢ÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂ¦ÃÂÃÂ¥ÃÂ¿ÃÂµÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¦ÃÂÃÂ§ÃÂ£ÃÂÃÂ"""
    v = _get_validator()
    results = v.validate_all(domain)
    return {
        "domain": domain,
        "results": [r.to_dict() for r in results],
        "count": len(results),
    }


@router.get("/rules", summary="ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂºÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂÃÂ¥ÃÂÃÂ")
async def list_rules() -> dict[str, Any]:
    """ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂºÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂ·ÃÂ²ÃÂ¦ÃÂ³ÃÂ¨ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂÃÂ¥ÃÂÃÂÃÂ£ÃÂÃÂ"""
    v = _get_validator()
    return {"rules": v.list_rules(), "count": len(v.list_rules())}
