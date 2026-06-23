"""知识查询 API（Step 3.4b）。

GET /api/v1/knowledge?domain=accounting&concept=CurrentRatio
GET /api/v1/knowledge/concepts?domain=accounting
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orbit.knowledge.engine import KnowledgeEngine, QueryMode

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# WHY 模块级单例：KnowledgeEngine 包装 SQLite，
# 惰性初始化，多 worker 共享同一 DB 文件（SQLite WAL 支持并发读）。
_engine: KnowledgeEngine | None = None


def _get_engine() -> KnowledgeEngine:
    global _engine
    if _engine is None:
        _engine = KnowledgeEngine()
    return _engine


@router.get("", summary="查询知识概念")
async def query_knowledge(
    domain: str = Query(..., min_length=1, description="领域：accounting/finance/legal"),
    concept: str = Query(..., min_length=1, description="概念名：CurrentRatio/ROE 等"),
    mode: QueryMode = Query("exact", description="查询模式"),  # noqa: B008
) -> dict[str, Any]:
    """精确查询领域知识概念。

    AC1: 零 Token，<50ms 响应。
    semantic/hybrid 模式当前降级为 exact（3.4c 实现）。
    """
    engine = _get_engine()
    result = engine.query(domain=domain, concept=concept, mode=mode)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"概念 {domain}/{concept} 不存在",
        )
    return result.to_dict()


@router.get("/search", summary="语义搜索")
async def search_knowledge(
    q: str = Query(..., min_length=1, description="自然语言查询"),
    top_k: int = Query(5, ge=1, le=20, description="返回数量"),
) -> dict[str, Any]:
    """语义搜索——用自然语言查询知识概念。"""
    engine = _get_engine()
    results = engine.search(q, top_k=top_k)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/concepts", summary="列出领域概念")
async def list_concepts(
    domain: str = Query("accounting", min_length=1, description="领域"),
) -> dict[str, Any]:
    """列出某领域所有概念（简要清单）。"""
    engine = _get_engine()
    concepts = engine.list_concepts(domain)
    return {"domain": domain, "concepts": concepts, "count": len(concepts)}
