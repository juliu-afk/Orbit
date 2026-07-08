"""因果推理 API 端点 (V14.2+Theory 方向 1).

端点:
  POST /api/v1/causal/learn       —— 从轨迹数据学习因果图
  POST /api/v1/causal/root-cause  —— 查询任务失败根因
  GET  /api/v1/causal/graph        —— 获取当前因果图（供驾驶舱可视化）
  POST /api/v1/causal/recommend    —— 基于根因生成改进建议
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.causal.graph import CausalModelManager
    from orbit.causal.root_cause import RootCauseAnalyzer
    from orbit.causal.recommend import CausalRecommender

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/causal", tags=["causal"])


# ── 请求/响应模型 ──────────────────────────────────

class LearnRequest(BaseModel):
    min_samples: int = Field(50, ge=10, le=10000,
                             description="最低样本数——低于此值不学习")


class RootCauseRequest(BaseModel):
    task_id: str = Field(..., min_length=1, description="失败任务的 ID")


class RecommendRequest(BaseModel):
    task_id: str = Field(..., min_length=1)


class LearnResponse(BaseModel):
    edges: int
    sample_size: int
    learned_at: float
    fit_quality: float


class RootCauseResponse(BaseModel):
    task_id: str
    top_cause: dict | None
    causes: list[dict]
    confidence: float
    explanation_failed: bool
    missing_variables: list[str]


class GraphResponse(BaseModel):
    variables: list[str]
    edges: list[dict]
    learned_at: float
    sample_size: int


class RecommendResponse(BaseModel):
    recommendations: list[dict]


# ── 依赖注入 ────────────────────────────────────────

# 这些实例由 lifespan 或 main.py 设置
_causal_manager: CausalModelManager | None = None
_root_cause_analyzer: RootCauseAnalyzer | None = None
_causal_recommender: CausalRecommender | None = None


def setup_causal(
    manager: CausalModelManager,
    analyzer: RootCauseAnalyzer,
    recommender: CausalRecommender,
) -> None:
    """注入因果推理组件——由 main.py/lifespan 调用。"""
    global _causal_manager, _root_cause_analyzer, _causal_recommender
    _causal_manager = manager
    _root_cause_analyzer = analyzer
    _causal_recommender = recommender


def _check_setup():
    if _causal_manager is None:
        raise HTTPException(503, "因果推理引擎未初始化——轨迹数据不足或服务未就绪")


# ── 端点 ────────────────────────────────────────────

@router.post("/learn", response_model=dict)
async def learn_causal_graph(req: LearnRequest):
    """从轨迹数据学习因果图。

    调用 DoWhy GCM 的 assign_causal_mechanisms + fit。
    需要至少 req.min_samples 条已完成轨迹。
    """
    _check_setup()
    assert _causal_manager is not None
    graph = await _causal_manager.fit(min_samples=req.min_samples)
    return {
        "code": 0,
        "data": LearnResponse(
            edges=len(graph.edges),
            sample_size=graph.sample_size,
            learned_at=graph.learned_at,
            fit_quality=graph.fit_quality,
        ).model_dump(),
        "message": "ok" if graph.fit_quality > 0
                   else "轨迹数据不足或 GCM 拟合失败——已降级",
    }


@router.post("/root-cause", response_model=dict)
async def get_root_cause(req: RootCauseRequest):
    """查询任务失败根因。

    用 DoWhy GCM attribute_anomalies() 归因异常到上游节点。
    如果因果模型不可用，降级为相关性排序。
    """
    _check_setup()
    assert _root_cause_analyzer is not None
    root_cause = await _root_cause_analyzer.analyze(req.task_id)

    causes_data = [
        {
            "variable": c.variable,
            "anomaly_score": c.anomaly_score,
            "explanation": c.explanation,
            "counterfactual": c.counterfactual,
        }
        for c in root_cause.causes
    ]
    top = None
    if root_cause.top_cause:
        top = {
            "variable": root_cause.top_cause.variable,
            "anomaly_score": root_cause.top_cause.anomaly_score,
            "explanation": root_cause.top_cause.explanation,
            "counterfactual": root_cause.top_cause.counterfactual,
        }

    return {
        "code": 0,
        "data": RootCauseResponse(
            task_id=root_cause.task_id,
            top_cause=top,
            causes=causes_data,
            confidence=root_cause.confidence,
            explanation_failed=root_cause.explanation_failed,
            missing_variables=root_cause.missing_variables,
        ).model_dump(),
        "message": "ok",
    }


@router.get("/graph", response_model=dict)
async def get_causal_graph():
    """获取当前因果图——供驾驶舱可视化（P1）。

    边颜色: causal_strength, 节点大小: 连接度。
    返回 JSON 可直接喂给 Cytoscape.js 或 ECharts。
    """
    _check_setup()
    assert _causal_manager is not None
    graph = _causal_manager.last_graph
    if graph is None:
        return {"code": 0, "data": None, "message": "因果图尚未学习——先调用 POST /learn"}
    return {
        "code": 0,
        "data": GraphResponse(
            variables=graph.variables,
            edges=[e.model_dump() for e in graph.edges],
            learned_at=graph.learned_at,
            sample_size=graph.sample_size,
        ).model_dump(),
        "message": "ok",
    }


@router.post("/recommend", response_model=dict)
async def get_recommendations(req: RecommendRequest):
    """基于根因生成改进建议。

    先用 RootCauseAnalyzer 找到根因，再用 CausalRecommender 生成建议。
    LLM 可用时生成人类可读建议，不可用时降级为固定映射。
    """
    _check_setup()
    assert _root_cause_analyzer is not None
    assert _causal_recommender is not None
    root_cause = await _root_cause_analyzer.analyze(req.task_id)
    recs = await _causal_recommender.recommend(root_cause)
    return {
        "code": 0,
        "data": RecommendResponse(
            recommendations=[r.model_dump() for r in recs],
        ).model_dump(),
        "message": "ok",
    }
