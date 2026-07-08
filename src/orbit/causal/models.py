"""因果推理引擎数据模型.

Pydantic v2 模型——因果图、根因分析、异常归因结果。
DoWhy GCM 对象不入模型（运行时持有，不序列化）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CausalEdge(BaseModel):
    """单条因果边。"""
    source_var: str
    target_var: str
    causal_strength: float = Field(0.0, ge=0.0, le=1.0)  # DoWhy arrow_strength()
    confidence: float = Field(0.0, ge=0.0, le=1.0)         # bootstrap 置信度
    avg_causal_effect: float | None = None                  # E[Y|do(X=x₁)] - E[Y|do(X=x₀)]
    sample_count: int = 0


class CausalGraph(BaseModel):
    """DoWhy GCM 拟合后的因果图（序列化用）。

    底层 DoWhy GCM 对象通过 _gcm_model 持有——不入模型，不序列化。
    """
    variables: list[str] = Field(default_factory=list)
    edges: list[CausalEdge] = Field(default_factory=list)
    learned_at: float = 0.0
    sample_size: int = 0
    fit_quality: float = Field(0.0, ge=0.0, le=1.0, description="GCM 拟合 R² 均值")


class CauseCandidate(BaseModel):
    """单个根因候选——一个变量的异常贡献。"""
    variable: str                                    # 变量名
    anomaly_score: float = Field(0.0, ge=0.0)         # DoWhy gcm.attribute_anomalies() 输出
    causal_effect: float | None = None                # do-calculus 因果效应
    explanation: str = ""                             # LLM 人类可读解释（P1）
    counterfactual: str = ""                          # 反事实建议


class RootCause(BaseModel):
    """失败根因分析结果。"""
    task_id: str
    causes: list[CauseCandidate] = Field(default_factory=list)  # 异常分数降序
    top_cause: CauseCandidate | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    explanation_failed: bool = False                  # LLM 解释是否降级
    missing_variables: list[str] = Field(default_factory=list)  # 轨迹中缺失的变量
    stale: bool = False                               # 因果图是否过期
