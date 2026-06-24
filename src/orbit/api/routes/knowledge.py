"""Ã§ÂÂ¥Ã¨Â¯ÂÃ¦ÂÂ¥Ã¨Â¯Â¢ APIÃ¯Â¼ÂStep 3.4bÃ¯Â¼ÂÃ£ÂÂ

GET /api/v1/knowledge?domain=accounting&concept=CurrentRatio
GET /api/v1/knowledge/concepts?domain=accounting
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orbit.knowledge.engine import KnowledgeEngine, QueryMode

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# WHY Ã¦Â¨Â¡Ã¥ÂÂÃ§ÂºÂ§Ã¥ÂÂÃ¤Â¾ÂÃ¯Â¼ÂKnowledgeEngine Ã¥ÂÂÃ¨Â£Â SQLiteÃ¯Â¼Â
# Ã¦ÂÂ°Ã¦ÂÂ§Ã¥ÂÂÃ¥Â§ÂÃ¥ÂÂÃ¯Â¼ÂÃ¥Â¤Â worker Ã¥ÂÂ±Ã¤ÂºÂ«Ã¥ÂÂÃ¤Â¸Â DB Ã¦ÂÂÃ¤Â»Â¶Ã¯Â¼ÂSQLite WAL Ã¦ÂÂ¯Ã¦ÂÂÃ¥Â¹Â¶Ã¥ÂÂÃ¨Â¯Â»Ã¯Â¼ÂÃ£ÂÂ
_engine: KnowledgeEngine | None = None


def _get_engine() -> KnowledgeEngine:
    global _engine
    if _engine is None:
        try:
            _engine = KnowledgeEngine()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"知识库不可用: {e}") from e
    return _engine


@router.get("", summary="Ã¦ÂÂ¥Ã¨Â¯Â¢Ã§ÂÂ¥Ã¨Â¯ÂÃ¦Â¦ÂÃ¥Â¿Âµ")
async def query_knowledge(
    domain: str = Query(
        ..., min_length=1, description="Ã©Â¢ÂÃ¥ÂÂÃ¯Â¼Âaccounting/finance/legal"
    ),
    concept: str = Query(
        ..., min_length=1, description="Ã¦Â¦ÂÃ¥Â¿ÂµÃ¥ÂÂÃ¯Â¼ÂCurrentRatio/ROE Ã§Â­Â"
    ),
    mode: QueryMode = Query("exact", description="Ã¦ÂÂ¥Ã¨Â¯Â¢Ã¦Â¨Â¡Ã¥Â¼Â"),  # noqa: B008
) -> dict[str, Any]:
    """Ã§Â²Â¾Ã§Â¡Â®Ã¦ÂÂ¥Ã¨Â¯Â¢Ã©Â¢ÂÃ¥ÂÂÃ§ÂÂ¥Ã¨Â¯ÂÃ¦Â¦ÂÃ¥Â¿ÂµÃ£ÂÂ

    AC1: Ã©ÂÂ¶ TokenÃ¯Â¼Â<50ms Ã¥ÂÂÃ¥ÂºÂÃ£ÂÂ
    semantic/hybrid Ã¦Â¨Â¡Ã¥Â¼ÂÃ¥Â½ÂÃ¥ÂÂÃ©ÂÂÃ§ÂºÂ§Ã¤Â¸Âº exactÃ¯Â¼Â3.4c Ã¥Â®ÂÃ§ÂÂ°Ã¯Â¼ÂÃ£ÂÂ
    """
    engine = _get_engine()
    result = engine.query(domain=domain, concept=concept, mode=mode)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ã¦Â¦ÂÃ¥Â¿Âµ {domain}/{concept} Ã¤Â¸ÂÃ¥Â­ÂÃ¥ÂÂ¨",
        )
    return result.to_dict()


@router.get("/search", summary="Ã¨Â¯Â­Ã¤Â¹ÂÃ¦ÂÂÃ§Â´Â¢")
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Ã¨ÂÂªÃ§ÂÂ¶Ã¨Â¯Â­Ã¨Â¨ÂÃ¦ÂÂ¥Ã¨Â¯Â¢"),
    top_k: int = Query(5, ge=1, le=20, description="Ã¨Â¿ÂÃ¥ÂÂÃ¦ÂÂ°Ã©ÂÂ"),
) -> dict[str, Any]:
    """Ã¨Â¯Â­Ã¤Â¹ÂÃ¦ÂÂÃ§Â´Â¢Ã¢ÂÂÃ¢ÂÂÃ§ÂÂ¨Ã¨ÂÂªÃ§ÂÂ¶Ã¨Â¯Â­Ã¨Â¨ÂÃ¦ÂÂ¥Ã¨Â¯Â¢Ã§ÂÂ¥Ã¨Â¯ÂÃ¦Â¦ÂÃ¥Â¿ÂµÃ£ÂÂ"""
    engine = _get_engine()
    results = engine.search(q, top_k=top_k)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/concepts", summary="Ã¥ÂÂÃ¥ÂÂºÃ©Â¢ÂÃ¥ÂÂÃ¦Â¦ÂÃ¥Â¿Âµ")
async def list_concepts(
    domain: str = Query("accounting", min_length=1, description="Ã©Â¢ÂÃ¥ÂÂ"),
) -> dict[str, Any]:
    """Ã¥ÂÂÃ¥ÂÂºÃ¦ÂÂÃ©Â¢ÂÃ¥ÂÂÃ¦ÂÂÃ¦ÂÂÃ¦Â¦ÂÃ¥Â¿ÂµÃ¯Â¼ÂÃ§Â®ÂÃ¨Â¦ÂÃ¦Â¸ÂÃ¥ÂÂÃ¯Â¼ÂÃ£ÂÂ"""
    engine = _get_engine()
    concepts = engine.list_concepts(domain)
    return {"domain": domain, "concepts": concepts, "count": len(concepts)}
