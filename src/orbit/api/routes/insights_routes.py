"""Phase 3 智能洞察 API——风险评分/影响分析/模块健康."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/insights", tags=["insights"])

# P2-5: 全局变量显式类型
_code_graph: Any = None
_review_service: Any = None


def set_code_graph(engine: Any) -> None:
    global _code_graph
    _code_graph = engine


def set_review_service(svc: Any) -> None:
    global _review_service
    _review_service = svc


class RiskScore(BaseModel):
    file: str
    # P2-1: score 范围限制 0-100
    score: int = Field(..., ge=0, le=100)
    # P1-3: Literal 约束
    level: Literal["low", "medium", "high"]
    factors: list[str]


class ImpactNode(BaseModel):
    name: str
    file: str
    # P2-2: Literal 约束避免无效 CSS class
    level: Literal["direct", "indirect"]
    callers: list[str]


@router.get("/risk", response_model=list[RiskScore])
async def risk_scores(task_id: str = Query(...)):
    """风险评分——从审查数据计算文件级风险分数 (Phase 3.1)."""
    if _review_service is None:
        return []
    try:
        review_data = await _review_service.get_summary(task_id)
        files = review_data.get("files", {})
        if not files:
            return []
        scores: list[RiskScore] = []
        for fp, stats in files.items():
            approved = stats.get("approved", 0)
            rejected = stats.get("rejected", 0)
            total = approved + rejected
            if total == 0:
                score = 0
                level: Literal["low", "medium", "high"] = "low"
            else:
                score = min(100, round(rejected / total * 100))
                level = "high" if score > 66 else "medium" if score > 33 else "low"
            factors = [f"approved={approved}", f"rejected={rejected}"]
            scores.append(RiskScore(file=fp, score=score, level=level, factors=factors))
        return sorted(scores, key=lambda x: x.score, reverse=True)
    except (ValueError, RuntimeError) as e:
        # P1-1: 精确异常捕获 + 日志
        import structlog

        structlog.get_logger().warning("risk_score_failed", error=str(e))
        return []


@router.get("/impact")
async def impact_analysis(symbol: str = Query(...)):
    """影响分析——CodeGraph 依赖图高亮受影响模块 (Phase 3.1)."""
    if _code_graph is None:
        return []
    try:
        callers = await _code_graph.get_callers(symbol)
        # 区分 direct vs indirect
        nodes: list[ImpactNode] = [
            ImpactNode(name=c, file="", level="direct", callers=[]) for c in callers[:10]
        ]
        return nodes
    except (RuntimeError, ValueError) as e:
        import structlog

        structlog.get_logger().warning("impact_analysis_failed", error=str(e))
        return []


@router.get("/health")
async def module_health():
    """模块健康仪表盘——预留接口，后续接入 AgentOps 实际数据 (Phase 3.4)."""
    return {"modules": [], "note": "Module health data will be populated from AgentOps metrics"}
